from hashlib import md5
from smtplib import SMTP, SMTP_SSL, SMTPException
from logging import getLogger
from collections import defaultdict
from socket import sslerror
from threading import Lock
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.utils import DNS_NAME
from django.core.mail.message import sanitize_address
from django.conf import settings
from django_ztaskq.decorators import ztask
from .utils import get_setting


class MalformedMessage(Exception):
    """The mail message is malformed or otherwise invalid
    """

    def __init__(self, message, mail_message):
        self.message = message
        self.mail_message = mail_message
        super(MalformedMessage, self).__init__(message, mail_message)

    def __str__(self):
        return "%s: %s" % (self.__class__.__name__, self.message)


class MessageWrapper(object):

    def __init__(self, message):
        self.mail_message = message
        self.retries = 0
        self.errors = []
        self.sent = False
        self.max_retries = get_setting('MAX_RETRIES')
        self.retry_step = get_setting('RETRY_STEP')
        self.retry_base = get_setting('RETRY_BASE')

    def send(self, connection):
        email_message = self.mail_message
        if not email_message.recipients():
            raise MalformedMessage("No recipients for message", email_message)
        from_email = sanitize_address(
            email_message.from_email,
            email_message.encoding
        )
        recipients = [
            sanitize_address(addr, email_message.encoding)
            for addr in email_message.recipients()
        ]
        try:
            connection.sendmail(
                from_email,
                recipients,
                email_message.message().as_string()
            )
        except SMTPException, e: # pylint: disable=W0703
            self.retries += 1
            self.errors.append(e)
        else:
            self.sent = True

    def must_resend(self):
        if not self.sent and self.retries <= self.max_retries:
            return True
        return False

    def resend_wait(self):
        return self.retry_step * (self.retry_base ** (self.retries - 1))

    @property
    def uid(self):
        message = self.mail_message.message()
        del message['Message-ID']
        del message['Date']
        return md5(message.as_string()).hexdigest()

    def __repr__(self):
        return "<MessageWrapper: from '%s' to '%s' (%s), retried %d>" % (
            self.mail_message.from_email,
            ", ".join(self.mail_message.recipients()),
            self.uid,
            self.retries
        )


class MailSender(object):

    def __init__(self):
        self.lock = Lock()
        self.host = settings.EMAIL_HOST
        self.port = settings.EMAIL_PORT
        self.username = settings.EMAIL_HOST_USER
        self.password = settings.EMAIL_HOST_PASSWORD
        self.use_ssl = getattr(settings, 'EMAIL_USE_SMTP_SSL', False)
        self.use_tls = settings.EMAIL_USE_TLS
        if self.use_ssl and self.use_tls:
            raise ImproperlyConfigured(
                "You must set either EMAIL_USE_SMTP_SSL or "
                "EMAIL_USE_TLS, not both"
            )
        self.connection = None

    def connect(self):
        kwargs = {
            'local_hostname': DNS_NAME.get_fqdn()
        }
        if self.use_ssl:
            keyfile = getattr(settings, 'EMAIL_SSL_KEYFILE', None)
            certfile = getattr(settings, 'EMAIL_SSL_CERTFILE', None)
            if keyfile:
                kwargs['keyfile'] = keyfile
            if certfile:
                kwargs['certfile'] = certfile
            self.connection = SMTP_SSL(self.host, self.port, **kwargs)
        else:
            self.connection = SMTP(self.host, self.port, **kwargs)
        if self.use_tls:
            self.connection.ehlo()
            self.connection.starttls()
            self.connection.ehlo()
        if self.username and self.password:
            self.connection.login(self.username, self.password)
        return True

    def disconnect(self):
        if self.connection is not None:
            try:
                self.connection.quit()
            except sslerror:
                # This happens when calling quit() on a TLS connection
                # sometimes.
                self.connection.close()

    def send_message(self, message, results):
        try:
            message.send(self.connection)
        except Exception, e: # pylint: disable=W0703
            message.errors.append(e)
            results['failed'].append(message)
        else:
            if message.sent:
                results['succesful'].append(message)
            else:
                results['retry'].append(message)

    def send(self, messages):
        logger = getLogger("django_ztaskq_mailer")
        results = {
            'succesful': [],
            'retry': [],
            'failed': []
        }
        retries = defaultdict(list)
        with self.lock:
            try:
                self.connect()
            except SMTPException, e:
                for message in messages:
                    message.errors.append(e)
                    message.retries += 1
                    results['retry'].append(message)
            else:
                for message in messages:
                    self.send_message(message, results)
            while len(results['retry']) > 0:
                message = results['retry'].pop()
                if message.must_resend():
                    retries[message.resend_wait()].append(message)
                else:
                    results['failed'].append(message)
            for delay, messages in retries.items():
                results['retry'].extend(messages)
                sendmail.async(messages, ztaskq_delay=delay)
            if len(results['failed']) > 0:
                for message in results['failed']:
                    logger.error(
                        ("Could not send message "
                         "because the following errors occurred:\n%s"
                         "\nOriginal message was:\n%s\n\n") % (
                            "\n".join([ str(m) for m in message.errors ]),
                            message.mail_message.message().as_string(),
                        )
                    )
            self.disconnect()
        return results


sender = MailSender()


@ztask()
def sendmail(messages):
    sender.send(messages)


class EmailBackend(BaseEmailBackend):

    def send_messages(self, messages):
        sendmail.async([
            MessageWrapper(m) for m in messages
        ])


def test_send(from_, to):
    """This is merely used to be invoked from django shell
    to troubleshoot failing servers
    """
    from django.core.mail.message import EmailMessage
    mail = EmailMessage(
        'Test message',
        'Just a test message',
        from_,
        to=to
    )
    sendmail([ MessageWrapper(mail) ])
