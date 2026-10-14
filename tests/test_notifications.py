import unittest
from notification_utils import IncomingNotificationTracker, alert_content


def msg(i, sim=2, direction='incoming', text='Hej'):
    return {'id':str(i),'phone':'+46701234567','date':f'2026-10-08T12:00:{i%60:02d}+02:00',
            'sim':sim,'direction':direction,'text':text}

class NotificationTests(unittest.TestCase):
    def test_initial_history_is_quiet(self):
        watcher=IncomingNotificationTracker()
        self.assertEqual(watcher.ingest([msg(1),msg(2)],2),[])
        self.assertTrue(watcher.ready)
        self.assertEqual(watcher.ingest([msg(1),msg(2)],2),[])

    def test_new_received_once_and_not_outgoing(self):
        watcher=IncomingNotificationTracker();watcher.ingest([msg(1)],2)
        self.assertEqual(watcher.ingest([msg(1),msg(3),msg(4,direction='outgoing')],2),[msg(3)])
        self.assertEqual(watcher.ingest([msg(3),msg(1)],2),[])

    def test_strict_sim_does_not_alert_cross_sim(self):
        watcher=IncomingNotificationTracker();watcher.ingest([],2)
        self.assertEqual(watcher.ingest([msg(5,sim=1)],2),[])
        self.assertEqual(watcher.ingest([msg(5,sim=1)],1),[])
        self.assertEqual(watcher.ingest([msg(5,sim=1),msg(6,sim=1)],1),[msg(6,sim=1)])

    def test_unknown_sim_user_opt_in(self):
        watcher=IncomingNotificationTracker();watcher.ingest([],2)
        self.assertEqual(watcher.ingest([msg(7,sim=None)],2,False),[])
        self.assertEqual(watcher.ingest([msg(7,sim=None),msg(8,sim=None)],2,True),[msg(8,sim=None)])

    def test_id_no_duplicates_in_single_poll(self):
        watcher=IncomingNotificationTracker();watcher.ingest([],2)
        self.assertEqual(len(watcher.ingest([msg(9),msg(9)],2)),1)

    def test_previews_are_optional_and_truncated(self):
        title,body=alert_content([msg(2,text='super-secret')],False)
        self.assertNotIn('super-secret',title+body)
        _,body=alert_content([msg(2,text='super-secret')],True)
        self.assertIn('super-secret',body)
        _,body=alert_content([msg(2,text='x'*999)],True)
        self.assertLessEqual(len(body),181)
        self.assertIn('2 new messages',alert_content([msg(1),msg(2)],True)[0])

if __name__=='__main__':unittest.main()
