# !/usr/bin/env python3

import smtplib, ssl
from email.header import Header
from email.mime.text import MIMEText
from email.utils import parseaddr, formataddr

def _format_addr(s):
    name, addr = parseaddr(s)
    return formataddr((Header(name, 'utf-8').encode(), addr))


port = 465
smtp_server = "smtp.sina.com"
sender_email = "chenghit@sina.com"
receiver_email = "chenghit@qq.com"
password = 'c25f905226806a23'
# 因为新浪邮箱会校验邮件正文和From，所以需要为邮件正文添加一个前缀
pre = 'From:{}'.format(sender_email)


def send_email(message, port=port, smtp_server=smtp_server, sender_email=sender_email,
               receiver_email=receiver_email, password=password):
    msg = MIMEText('{}\n{}'.format(pre, message), 'plain', 'utf-8')
    msg['From'] = _format_addr('Python Demo <{}>'.format(sender_email))
    msg['To'] = _format_addr('Admin <{}>'.format(receiver_email))
    msg['Subject'] = Header('C9120异常告警', 'utf-8').encode()

    context = ssl.create_default_context()
    context.options |= ssl.OP_NO_TLSv1_2 | ssl.OP_NO_TLSv1_3
    context.minimum_version = ssl.TLSVersion ["TLSv1_1"]
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
        server.login(sender_email, password)
        server.sendmail(sender_email, receiver_email, msg.as_string())