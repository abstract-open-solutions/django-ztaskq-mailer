# -*- coding: utf-8 -*-
from smtplib import SMTPDataError
from mock import Mock
from unittest import TestCase
from django.core.mail.message import EmailMessage
from .backend import MessageWrapper, MalformedMessage


class MessageWrapperTest(TestCase):

    def setUp(self):
        self.connection = Mock(spec=['sendmail'])
        self.connection.sendmail.return_value = None
        self.faulty_connection = Mock(spec=['sendmail'])
        self.faulty_connection.sendmail.return_value = None
        self.faulty_connection.sendmail.side_effect = SMTPDataError(
            100,
            "Something wrong happened"
        )
        headers = {
            'Date': 'Thu, 30 Aug 2012 16:12:44 -0000',
            'Message-ID': '<20120830161244.12730.1173@hamlet>'
        }
        self.correct_email = EmailMessage(
            'Test message',
            'Just a test message',
            'john@example.com',
            to=['clint@example.com'],
            headers=headers
        )
        self.unicode_email = EmailMessage(
            u'Detta är ett testmeddelande',
            u'Detta test meddelande skrivs inte på danska.',
            u'Åke Skållström <ake@example.com>',
            to=[u'Björn Borg <bjorn@example.com>'],
            headers=headers
        )
        self.malformed_email = EmailMessage(
            'Test message',
            'Just a test message',
            'john@example.com',
            headers=headers
        )

    def test_instantiation(self):
        message = MessageWrapper(self.correct_email)
        self.assertEqual(message.retries, 0)
        self.assertEqual(message.sent, False)
        self.assertEqual(message.errors, [])

    def test_send(self):
        message = MessageWrapper(self.correct_email)
        message.send(self.connection)
        self.assertEqual(message.retries, 0)
        self.assertEqual(message.sent, True)
        self.assertEqual(message.errors, [])
        self.connection.sendmail.assert_called_once_with(
            'john@example.com',
            ['clint@example.com'],
            ('Content-Type: text/plain; charset="utf-8"\n'
             'MIME-Version: 1.0\n'
             'Content-Transfer-Encoding: 7bit\n'
             'Subject: Test message\n'
             'From: john@example.com\n'
             'To: clint@example.com\n'
             'Date: Thu, 30 Aug 2012 16:12:44 -0000\n'
             'Message-ID: <20120830161244.12730.1173@hamlet>\n\n'
             'Just a test message')
        )

    def test_send_unicode(self):
        message = MessageWrapper(self.unicode_email)
        message.send(self.connection)
        self.assertEqual(message.retries, 0)
        self.assertEqual(message.sent, True)
        self.assertEqual(message.errors, [])
        self.connection.sendmail.assert_called_once_with(
            '=?utf-8?b?w4VrZSBTa8OlbGxzdHLDtm0=?= <ake@example.com>',
            ['=?utf-8?q?Bj=C3=B6rn_Borg?= <bjorn@example.com>'],
            ('Content-Type: text/plain; charset="utf-8"\n'
             'MIME-Version: 1.0\n'
             'Content-Transfer-Encoding: 8bit\n'
             'Subject: =?utf-8?q?Detta_=C3=A4r_ett_testmeddelande?=\n'
             'From: =?utf-8?b?w4VrZSBTa8OlbGxzdHLDtm0=?= <ake@example.com>\n'
             'To: =?utf-8?q?Bj=C3=B6rn_Borg?= <bjorn@example.com>\n'
             'Date: Thu, 30 Aug 2012 16:12:44 -0000\n'
             'Message-ID: <20120830161244.12730.1173@hamlet>\n\n'
             'Detta test meddelande skrivs inte p\xc3\xa5 danska.')
        )

    def test_send_wrong(self):
        message = MessageWrapper(self.malformed_email)
        with self.assertRaises(MalformedMessage):
            message.send(self.connection)
        self.assertEqual(message.retries, 0)
        self.assertEqual(message.sent, False)
        self.assertEqual(message.errors, [])
        self.assertEqual(self.connection.sendmail.called, False)

    def test_send_faulty(self):
        message = MessageWrapper(self.correct_email)
        message.send(self.faulty_connection)
        self.assertEqual(message.retries, 1)
        self.assertEqual(message.sent, False)
        self.assertEqual(len(message.errors), 1)
        self.assertTrue(isinstance(message.errors[0], SMTPDataError))

    def test_send_faulty_multiple(self):
        message = MessageWrapper(self.correct_email)
        message.send(self.faulty_connection)
        message.send(self.faulty_connection)
        message.send(self.faulty_connection)
        self.assertEqual(message.retries, 3)
        self.assertEqual(message.sent, False)
        self.assertEqual(len(message.errors), 3)
        for error in message.errors:
            self.assertTrue(isinstance(error, SMTPDataError))
