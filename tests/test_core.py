import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from core import (
    Gateway, GatewayError, all_messages, canonical_phone, iso_date, json_save,
    load_cache, load_settings, merge_items, message_visible, normalize_inbox,
    normalize_sent, unique_key, validate_url,
)


class CoreTests(unittest.TestCase):
    def test_sim_filter_strict(self):
        messages = [dict(sim=1),dict(sim=2),dict(sim=None)]
        self.assertEqual([message_visible(x,1) for x in messages],[True,False,False])
        self.assertEqual([message_visible(x,2) for x in messages],[False,True,False])
        self.assertEqual([message_visible(x,2,True) for x in messages],[False,True,True])

    def test_selected_sim_used_in_conversations(self):
        cache={'inbox':[
            {'id':'i1','date':'2026-10-08T12:00:00','phone':'+46701111111','text':'SIM1','sim':1,'direction':'incoming'},
            {'id':'i2','date':'2026-10-08T12:01:00','phone':'+46702222222','text':'SIM2','sim':2,'direction':'incoming'},
            {'id':'i3','date':'2026-10-08T12:02:00','phone':'+46703333333','text':'unknown','sim':None,'direction':'incoming'},
        ],'sent':[], 'local_sent':[]}
        self.assertEqual([x['text'] for x in all_messages(cache,1)],['SIM1'])
        self.assertEqual([x['text'] for x in all_messages(cache,2)],['SIM2'])
        self.assertEqual([x['text'] for x in all_messages(cache,2,True)],['SIM2','unknown'])

    def test_authoritative_sent_state_wins_over_local_queued(self):
        shared = {'id':'id-1','date':'2026-10-08T12:00:00','phone':'+46701234567',
                  'text':'Hej','direction':'outgoing'}
        cache={'inbox':[], 'local_sent':[dict(shared,sim=2,state='Queued (accepted by API)')],
               'sent':[dict(shared,sim=None,state='Delivered')]}
        result=all_messages(cache,2)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['sim'],2)
        self.assertEqual(result[0]['state'],'Delivered')

    def test_country_phone_variants(self):
        self.assertEqual(canonical_phone('070-123 45 67', '46'),canonical_phone('+46 70 123 45 67', '46'))
        self.assertEqual(canonical_phone('0046701234567'),canonical_phone('+46701234567'))

    def test_merge_keeps_known_sim_and_text(self):
        old=[{'direction':'outgoing','id':'abc','phone':'+46701234567','text':'hello','sim':2,'state':'Queued','date':'2026-10-08'}]
        new=[{'direction':'outgoing','id':'abc','phone':'0701234567','text':'','sim':None,'state':'Delivered','date':'2026-10-08'}]
        result=merge_items(old,new,country_code='46')
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['sim'],2)
        self.assertEqual(result[0]['text'],'hello')
        self.assertEqual(result[0]['state'],'Delivered')

    def test_different_recipients_on_same_gateway_id(self):
        x={'direction':'outgoing','id':'batch','phone':'+46701111111','text':'hello','sim':1,'date':'2026-10-08'}
        y=dict(x,phone='+46702222222')
        self.assertEqual(len(merge_items([x],[y])),2)

    def test_normalize_inbox(self):
        row=normalize_inbox({'id':'a','createdAt':'2026-10-08T12:00:00+02:00',
                             'sender':'ABFA','contentPreview':'سلام','simNumber':2,'type':'SMS'})
        self.assertEqual(row['sim'],2)
        self.assertEqual(row['text'],'سلام')

    def test_normalize_sent_recipients(self):
        rows=normalize_sent({'id':'sent123','state':'Delivered','textMessage':{'text':'Tack'},
                              'recipients':[{'phoneNumber':'+46701111111'}, {'phoneNumber':'+46702222222'}]})
        self.assertEqual(len(rows),2)
        self.assertTrue(all(x['direction']=='outgoing' for x in rows))

    def test_legacy_cache_migration_and_survives(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'messages.json'
            p.write_text(json.dumps({'inbox':[{'id':'x','date':'2026-10-08','phone':'0701234567','text':'Hi','sim':1}],
                                     'sent':[],'local_sent':[]}),encoding='utf-8')
            restored=load_cache(p)
            self.assertEqual(restored['inbox'][0]['direction'],'incoming')
            json_save(p,restored)
            self.assertEqual(load_cache(p)['inbox'][0]['text'],'Hi')

    def test_corrupted_cache_backed_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'messages.json';p.write_text('{broken')
            self.assertEqual(load_cache(p)['inbox'],[])
            self.assertEqual(len(list(Path(tmp).glob('messages.json.corrupt-*'))),1)

    def test_settings_default_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'settings.json';p.write_text('{"interval":"oops","sim":900,"theme":"bad"}')
            s=load_settings(p)
            self.assertEqual(s['interval'],60)
            self.assertEqual(s['sim'],1)
            self.assertEqual(s['theme'],'dark')

    def test_reject_public_url_and_redirect_credentials(self):
        for url in ['https://google.com','http://8.8.8.8:8080',
                    'http://192.168.1.10:8080/redirect','http://foo:pass@192.168.1.10:8080']:
            with self.subTest(url=url),self.assertRaises(ValueError):validate_url(url)
        self.assertEqual(validate_url('http://192.168.1.10:8080/'),'http://192.168.1.10:8080')

    def test_requests_never_follow_redirect(self):
        gateway=Gateway('http://192.168.1.10:8080','sms','hidden')
        response=Mock(status_code=302)
        with patch('core.requests.request',return_value=response) as mock_call:
            with self.assertRaises(GatewayError):gateway.health()
        self.assertIs(mock_call.call_args.kwargs['allow_redirects'],False)

    def test_send_sim2_exactly_once(self):
        gateway=Gateway('http://192.168.1.10:8080','sms','hidden')
        response=Mock(status_code=202)
        response.json.return_value={'id':'send-1'}
        with patch('core.requests.request',return_value=response) as mock_call:
            result=gateway.send('+46701234567','Hej!',2)
        self.assertEqual(result['id'],'send-1')
        self.assertEqual(mock_call.call_count,1)
        self.assertEqual(mock_call.call_args.kwargs['json']['simNumber'],2)
        self.assertEqual(mock_call.call_args.kwargs['json']['phoneNumbers'],['+46701234567'])

    def test_empty_202_counts_as_queued(self):
        gateway=Gateway('http://192.168.1.10:8080','sms','hidden')
        response=Mock(status_code=202)
        response.json.side_effect=ValueError('No content')
        with patch('core.requests.request',return_value=response):
            self.assertTrue(gateway.send('+46701234567','Hej!',1)['accepted'])

    def test_no_retry_on_ambiguous_send_timeout(self):
        gateway=Gateway('http://192.168.1.10:8080','sms','hidden')
        from requests.exceptions import ReadTimeout
        with patch('core.requests.request',side_effect=ReadTimeout('secret')) as mock_call:
            with self.assertRaisesRegex(GatewayError,'Do not retry'):
                gateway.send('+46701234567','Hej!',1)
            self.assertEqual(mock_call.call_count,1)

    def test_pagination_does_not_loop_if_server_ignores_offset(self):
        gateway=Gateway('http://192.168.1.10:8080','sms','hidden')
        items=[{'id':str(i)} for i in range(200)]
        with patch.object(gateway,'request',return_value=items) as called:
            result=gateway.collection('/inbox',max_rows=2000)
        self.assertEqual(len(result),200)
        self.assertEqual(called.call_count,2)

    def test_date_format(self):
        self.assertEqual(iso_date('2026-10-08T14:00:00+02:00')[:10],'2026-10-08')
        self.assertEqual(iso_date('not-a-date'),'not-a-date')


if __name__=='__main__': unittest.main()
