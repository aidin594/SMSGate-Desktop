"""Regression coverage for the missing outgoing messages in v4.1.

Uses synthetic API responses, never connects to a gateway or sends an SMS.
"""
import tempfile
import unittest
from pathlib import Path
from core import (all_messages, group_conversations, json_save, load_cache,
                  load_settings, normalize_sent, sent_message_date)

class SentVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.cache = {
            'inbox': [
                dict(id='in2',phone='+46700000111',text='Can you service?',
                     date='2026-10-08T13:16:00+02:00',direction='incoming',sim=2,state='SMS'),
                dict(id='in1',phone='+46711111111',text='SIM1 incoming',
                     date='2026-10-08T14:01:00+02:00',direction='incoming',sim=1,state='SMS'),
                dict(id='in?',phone='+46799999999',text='Unassigned incoming',
                     date='2026-10-08T14:05:00+02:00',direction='incoming',sim=None,state='SMS')
            ],
            'sent': [
                dict(id='out?',phone='0700000111',text='Your bike is ready',
                     date='2026-10-08T13:14:00+02:00',direction='outgoing',sim=None,state='Delivered'),
                dict(id='out1',phone='+46700000111',text='SIM1 send',
                     date='2026-10-08T13:15:00+02:00',direction='outgoing',sim=1,state='Sent'),
                dict(id='out2',phone='+46700000111',text='SIM2 send',
                     date='2026-10-08T13:17:00+02:00',direction='outgoing',sim=2,state='Sent')
            ],
            'local_sent': []
        }

    def test_unknown_outgoing_visible_with_sim2_by_default(self):
        messages=all_messages(self.cache,2,country_code='46')
        self.assertEqual({x['id'] for x in messages},{'in2','out?','out2'})
        self.assertNotIn('out1',{x['id'] for x in messages})
        conversation=group_conversations(messages,country_code='46')['46700000111']
        self.assertEqual(len(conversation),3)
        self.assertEqual({x['direction'] for x in conversation},{'incoming','outgoing'})
        self.assertIsNone(next(x for x in messages if x['id']=='out?')['sim'])

    def test_unknown_outgoing_visible_with_sim1_but_not_misattributed(self):
        messages=all_messages(self.cache,1)
        self.assertEqual({x['id'] for x in messages},{'in1','out?','out1'})
        self.assertIsNone(next(x for x in messages if x['id']=='out?')['sim'])

    def test_unknown_incoming_still_hidden_by_default(self):
        self.assertNotIn('in?',{x['id'] for x in all_messages(self.cache,2)})
        self.assertIn('in?',{x['id'] for x in all_messages(self.cache,2,include_unknown=True)})

    def test_strict_filter_can_hide_unassigned_outgoing(self):
        messages=all_messages(self.cache,2,show_unassigned_sent=False)
        self.assertEqual({x['id'] for x in messages},{'in2','out2'})

    def test_settings_migrate_defaults_on_existing_install(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'settings.json'
            json_save(target,{'sim':2,'theme':'light','include_unknown_sim':False})
            s=load_settings(target)
            self.assertTrue(s['show_unassigned_sent'])
            self.assertEqual(s['sim'],2)
            self.assertEqual(s['theme'],'light')

    def test_outgoing_states_can_supply_missing_timestamp(self):
        api_item={
            'id':'123','recipients':[{'phoneNumber':'+46700000111','state':'Delivered'}],
            'state':'Delivered','textMessage':{'text':'Repaired'},
            'states':{'Pending':'2026-10-08T12:00:00Z',
                      'Sent':'2026-10-08T12:02:00Z','Delivered':'2026-10-08T12:02:10Z'}
        }
        normalized=normalize_sent(api_item)
        self.assertEqual(len(normalized),1)
        self.assertEqual(normalized[0]['date'],'2026-10-08T12:00:00Z')
        self.assertIsNone(normalized[0]['sim'])
        self.assertEqual(normalized[0]['text'],'Repaired')

    def test_explicit_date_wins_over_states(self):
        self.assertEqual(sent_message_date({'createdAt':'2026-10-09','states':{'Sent':'2026-10-08T00:00:00Z'}}),'2026-10-09')

    def test_malformed_states_no_fabricated_timestamp(self):
        self.assertEqual(sent_message_date({'states':{'Sent':'none', 'Delivered':1234}}),'')

    def test_old_cache_survives_and_unassigned_sent_visible(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'messages.json'
            json_save(target,self.cache)
            result=load_cache(target)
            self.assertEqual(len(result['sent']),3)
            self.assertEqual({x['id'] for x in all_messages(result,2)},{'in2','out?','out2'})

    def test_sent_with_no_associated_inbox_still_accessible(self):
        cache={'inbox':[],'sent':[dict(id='only',phone='+46707555555',text='Outgoing only',
                                      direction='outgoing',sim=None,date='',state='Delivered')],
               'local_sent':[]}
        threads=group_conversations(all_messages(cache,2))
        self.assertIn('46707555555',threads)
        self.assertEqual(threads['46707555555'][0]['text'],'Outgoing only')

if __name__=='__main__': unittest.main()
