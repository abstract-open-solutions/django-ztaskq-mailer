import smtplib
from collections import defaultdict
from socket import sslerror
from threading import Lock
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
        except Exception, e: # pylint: disable=W0703
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


class MailSender(object):

    def __init__(self):
        self.lock = Lock()
        self.host = settings.EMAIL_HOST
        self.port = settings.EMAIL_PORT
        self.username = settings.EMAIL_HOST_USER
        self.password = settings.EMAIL_HOST_PASSWORD
        self.use_tls = settings.EMAIL_USE_TLS

    def connect(self):
        self.connection = smtplib.SMTP(self.host, self.port,
                                       local_hostname=DNS_NAME.get_fqdn())
        if self.use_tls:
            self.connection.ehlo()
            self.connection.starttls()
            self.connection.ehlo()
        if self.username and self.password:
            self.connection.login(self.username, self.password)
        return True

    def disconnect(self):
        try:
            self.connection.quit()
        except sslerror:
            # This happens when calling quit() on a TLS connection
            # sometimes.
            self.connection.close()

    def send(self, messages):
        with self.lock:
            self.connect()
            results = {
                'succesful': [],
                'retried': [],
                'failed': []
            }
            retries = defaultdict(list)
            for message in messages:
                try:
                    message.send(self.connection)
                except Exception, e: # pylint: disable=W0703
                    message.errors.append(e)
                    results['failed'].append(message)
                else:
                    if message.sent:
                        results['succesful'].append(message)
                    else:
                        if message.must_resend():
                            results['retried'].append(message)
                            retries[message.resend_wait()].append(message)
                        else:
                            results['failed'].append(message)
            for delay, messages in retries.items():
                sendmail.async(messages, ztaskq_delay=delay)
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
