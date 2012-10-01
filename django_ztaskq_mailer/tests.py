# -*- coding: utf-8 -*-
from smtplib import (SMTP, SMTP_SSL, SMTPException, SMTPConnectError,
                     SMTPHeloError, SMTPDataError, SMTPAuthenticationError,
                     SMTPRecipientsRefused, SMTPSenderRefused)
from mock import Mock, MagicMock, patch, call
from unittest import TestCase
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.message import EmailMessage
from django.test import TestCase as DjangoTestCase
from .backend import MessageWrapper, MalformedMessage, MailSender
from .utils import get_setting


class SettingsTest(DjangoTestCase):

    def test_default(self):
        with self.settings(ZTASKQ_MAILER={}):
            self.assertEqual(
                get_setting('MAX_RETRIES'),
                5
            )

    def test_override(self):
        with self.settings(ZTASKQ_MAILER={'MAX_RETRIES': 8}):
            self.assertEqual(
                get_setting('MAX_RETRIES'),
                8
            )


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


class SenderTest(DjangoTestCase):

    base_settings = {
        'EMAIL_HOST': 'localhost',
        'EMAIL_PORT': 25,
        'EMAIL_HOST_USER': '',
        'EMAIL_HOST_PASSWORD': '',
        'EMAIL_USE_TLS': False,
        'ZTASKQ_MAILER': {
            'MAX_RETRIES': 2,
            'RETRY_STEP': 30,
            'RETRY_BASE': 4
        }
    }

    normal_settings = base_settings.copy()

    tls_settings = base_settings.copy()
    tls_settings.update({
        'EMAIL_PORT': 587,
        'EMAIL_USE_TLS': True
    })

    ssl_settings = base_settings.copy()
    ssl_settings.update({
        'EMAIL_PORT': 465,
        'EMAIL_USE_SMTP_SSL': True
    })

    login_settings = base_settings.copy()
    login_settings.update({
        'EMAIL_HOST_USER': 'testuser',
        'EMAIL_HOST_PASSWORD': 'testpwd',
    })

    faulty_settings = base_settings.copy()
    faulty_settings.update({
        'EMAIL_PORT': 465,
        'EMAIL_USE_TLS': True,
        'EMAIL_USE_SMTP_SSL': True
    })

    def setUp(self):
        self.dns_patcher = patch('django_ztaskq_mailer.backend.DNS_NAME')
        self.DNS_NAME = self.dns_patcher.start()
        self.DNS_NAME.get_fqdn = MagicMock(return_value='localhost')
        self.sendmail_patcher = patch(
            'django_ztaskq_mailer.backend.sendmail')
        self.sendmail = self.sendmail_patcher.start()
        self.sendmail.async = MagicMock()
        self.smtplib = MagicMock()
        self.smtplib.mock_connection = MagicMock(spec=SMTP)
        self.smtplib.mock_ssl_connection = MagicMock(spec=SMTP_SSL)
        self.smtp_patcher = patch(
            'django_ztaskq_mailer.backend.SMTP',
            return_value=self.smtplib.mock_connection
        )
        self.smtp_ssl_patcher = patch(
            'django_ztaskq_mailer.backend.SMTP_SSL',
            return_value=self.smtplib.mock_ssl_connection
        )
        self.smtplib.SMTP = self.smtp_patcher.start()
        self.smtplib.SMTP_SSL = self.smtp_ssl_patcher.start()
        self.logger = MagicMock(
            spec=['debug', 'info', 'warning', 'error', 'exception']
        )
        self.getLogger_patcher = patch(
            'django_ztaskq_mailer.backend.getLogger',
            return_value=self.logger
        )
        self.getLogger = self.getLogger_patcher.start()

    def tearDown(self):
        self.dns_patcher.stop()
        self.sendmail_patcher.stop()
        self.smtp_patcher.stop()
        self.smtp_ssl_patcher.stop()
        self.getLogger_patcher.stop()

    def get_test_email(self):
        email = EmailMessage(
            'Test message',
            'Just a test message',
            'john@example.com',
            to=['clint@example.com'],
            headers = {
                'Date': 'Thu, 30 Aug 2012 16:12:44 -0000',
                'Message-ID': '<20120830161244.12730.1173@hamlet>'
            }
        )
        return (email, MessageWrapper(email))

    def test_config(self):
        with self.settings(**self.normal_settings):
            sender = MailSender()
            self.assertIsInstance(sender, MailSender)
        with self.settings(**self.faulty_settings):
            with self.assertRaises(ImproperlyConfigured):
                MailSender()

    def test_send(self):
        with self.settings(**self.normal_settings):
            sender = MailSender()
            __, wrapped = self.get_test_email()
            sender.send([ wrapped ])
            self.assertEqual(
                self.smtplib.SMTP.call_args_list,
                [
                    call('localhost', 25, local_hostname='localhost')
                ]
            )
            self.assertEqual(
                self.smtplib.mock_connection.login.call_count,
                0
            )
            self.assertEqual(
                self.smtplib.mock_connection.ehlo.call_count,
                0
            )
            self.assertEqual(
                self.smtplib.mock_connection.sendmail.call_count,
                1
            )
            self.assertEqual(
                self.smtplib.mock_connection.quit.call_args_list,
                [
                    call()
                ]
            )
            self.assertEqual(self.sendmail.async.call_count, 0)

    def test_send_login(self):
        with self.settings(**self.login_settings):
            sender = MailSender()
            __, wrapped = self.get_test_email()
            sender.send([ wrapped ])
            self.assertEqual(
                self.smtplib.SMTP.call_args_list,
                [
                    call('localhost', 25, local_hostname='localhost')
                ]
            )
            self.assertEqual(
                self.smtplib.mock_connection.login.call_args_list,
                [
                    call('testuser', 'testpwd')
                ]
            )
            self.assertEqual(
                self.smtplib.mock_connection.ehlo.call_count,
                0
            )
            self.assertEqual(
                self.smtplib.mock_connection.sendmail.call_count,
                1
            )
            self.assertEqual(
                self.smtplib.mock_connection.quit.call_count,
                1
            )
            self.assertEqual(self.sendmail.async.call_count, 0)

    def test_send_tls(self):
        with self.settings(**self.tls_settings):
            sender = MailSender()
            __, wrapped = self.get_test_email()
            sender.send([ wrapped ])
            self.assertEqual(
                self.smtplib.SMTP.call_args_list,
                [
                    call('localhost', 587, local_hostname='localhost')
                ]
            )
            self.assertEqual(
                self.smtplib.mock_connection.login.call_count,
                0
            )
            self.assertEqual(
                self.smtplib.mock_connection.ehlo.call_count,
                2
            )
            self.assertEqual(
                self.smtplib.mock_connection.starttls.call_count,
                1
            )
            self.assertEqual(
                self.smtplib.mock_connection.sendmail.call_count,
                1
            )
            self.assertEqual(
                self.smtplib.mock_connection.quit.call_count,
                1
            )
            self.assertEqual(self.sendmail.async.call_count, 0)

    def test_send_ssl(self):
        with self.settings(**self.ssl_settings):
            sender = MailSender()
            __, wrapped = self.get_test_email()
            sender.send([ wrapped ])
            self.assertEqual(
                self.smtplib.SMTP.call_count,
                0
            )
            self.assertEqual(
                self.smtplib.SMTP_SSL.call_args_list,
                [
                    call('localhost', 465, local_hostname='localhost')
                ]
            )
            self.assertEqual(
                self.smtplib.mock_ssl_connection.login.call_count,
                0
            )
            self.assertEqual(
                self.smtplib.mock_ssl_connection.ehlo.call_count,
                0
            )
            self.assertEqual(
                self.smtplib.mock_ssl_connection.sendmail.call_count,
                1
            )
            self.assertEqual(
                self.smtplib.mock_ssl_connection.quit.call_count,
                1
            )
            self.assertEqual(self.sendmail.async.call_count, 0)

    def assert_fail_sending(self, error_repr="(100, 'Whatever')"):
        sender = MailSender()
        __, wrapped = self.get_test_email()
        results = sender.send([ wrapped ])
        self.assertEqual(len(results['failed']), 0)
        self.assertEqual(len(results['retry']), 1)
        self.assertEqual(self.sendmail.async.call_count, 1)
        self.assertEqual(
            self.sendmail.async.call_args_list[-1],
            call(results['retry'], ztaskq_delay=30)
        )
        results = sender.send(results['retry'])
        self.assertEqual(len(results['failed']), 0)
        self.assertEqual(len(results['retry']), 1)
        self.assertEqual(self.sendmail.async.call_count, 2)
        self.assertEqual(
            self.sendmail.async.call_args_list[-1],
            call(results['retry'], ztaskq_delay=120)
        )
        results = sender.send(results['retry'])
        self.assertEqual(len(results['failed']), 1)
        self.assertEqual(len(results['retry']), 0)
        self.assertEqual(self.sendmail.async.call_count, 2)
        self.assertEqual(
            self.logger.error.call_args_list,
            [
                call(("Could not send message "
                      "because the following errors occurred:\n"
                      "%s\n"
                      "%s\n"
                      "%s\n"
                      "Original message was:\n%s\n\n") % (
                        error_repr,
                        error_repr,
                        error_repr,
                        results['failed'][0].mail_message.message()\
                            .as_string()
                     ))
            ]
        )

    def test_connect_fail(self):
        self.smtplib.SMTP.side_effect = SMTPConnectError(100, "Whatever")
        with self.settings(**self.normal_settings):
            self.assert_fail_sending()

    def test_tls_ehlo_fail(self):
        self.smtplib.mock_connection.ehlo.side_effect = SMTPHeloError(
            100,
            "Whatever"
        )
        with self.settings(**self.tls_settings):
            self.assert_fail_sending()

    def test_tls_starttls_fail(self):
        self.smtplib.mock_connection.starttls.side_effect = SMTPHeloError(
            100,
            "Whatever"
        )
        with self.settings(**self.tls_settings):
            self.assert_fail_sending()
        self.smtplib.mock_connection.starttls.side_effect = SMTPException(
            100,
            "Whatever"
        )
        self.sendmail.async.reset_mock()
        self.logger.error.reset_mock()
        with self.settings(**self.tls_settings):
            self.assert_fail_sending()

    def test_login_fail(self):
        self.smtplib.mock_connection.login.side_effect = SMTPHeloError(
            100,
            "Whatever"
        )
        with self.settings(**self.login_settings):
            self.assert_fail_sending()
        self.smtplib.mock_connection.login.side_effect = SMTPException(
            100,
            "Whatever"
        )
        self.sendmail.async.reset_mock()
        self.logger.error.reset_mock()
        with self.settings(**self.login_settings):
            self.assert_fail_sending()
        self.smtplib.mock_connection.login.side_effect = \
            SMTPAuthenticationError(100, "Whatever")
        self.sendmail.async.reset_mock()
        self.logger.error.reset_mock()
        with self.settings(**self.login_settings):
            self.assert_fail_sending()

    def test_send_fail(self):
        self.smtplib.mock_connection.sendmail.side_effect = SMTPHeloError(
            100,
            "Whatever"
        )
        with self.settings(**self.normal_settings):
            self.assert_fail_sending()
        self.smtplib.mock_connection.sendmail.side_effect = SMTPSenderRefused(
            100,
            "Whatever",
            'john@example.com'
        )
        self.sendmail.async.reset_mock()
        self.logger.error.reset_mock()
        with self.settings(**self.normal_settings):
            self.assert_fail_sending("(100, 'Whatever', 'john@example.com')")
        self.smtplib.mock_connection.sendmail.side_effect = \
            SMTPRecipientsRefused(['clint@example.com'])
        self.sendmail.async.reset_mock()
        self.logger.error.reset_mock()
        with self.settings(**self.normal_settings):
            self.assert_fail_sending("['clint@example.com']")
        self.smtplib.mock_connection.sendmail.side_effect = SMTPDataError(
            100,
            "Whatever"
        )
        self.sendmail.async.reset_mock()
        self.logger.error.reset_mock()
        with self.settings(**self.normal_settings):
            self.assert_fail_sending()


class BackendTest(DjangoTestCase):

    BACKEND_NAME = 'django_ztaskq_mailer.backend.EmailBackend'

    def setUp(self):
        self.sendmail_patcher = patch('django_ztaskq_mailer.backend.sendmail')
        self.sendmail = self.sendmail_patcher.start()
        self.sendmail.async = MagicMock()

    def tearDown(self):
        self.sendmail_patcher.stop()

    def test_sendmail(self):
        with self.settings(EMAIL_BACKEND=self.BACKEND_NAME):
            from django.core.mail import send_mail
            send_mail(
                'Subject here',
                'Here is the message.',
                'from@example.com',
                ['to@example.com'],
                fail_silently=False
            )
            self.assertEqual(self.sendmail.async.call_count, 1)
            self.assertEqual(self.sendmail.async.call_args_list[-1][1], {})
            self.assertEqual(
                len(self.sendmail.async.call_args_list[-1][0]),
                1
            )
            messages = self.sendmail.async.call_args_list[-1][0][0]
            self.assertEqual(len(messages), 1)
            self.assertIsInstance(messages[0], MessageWrapper)
            mail_message = messages[0].mail_message
            self.assertEqual(mail_message.from_email, 'from@example.com')
            self.assertEqual(mail_message.to, ['to@example.com'])
            self.assertEqual(mail_message.subject, 'Subject here')
            self.assertEqual(mail_message.body, 'Here is the message.')
