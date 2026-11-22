from __future__ import annotations
import asyncio
import smtplib
from email.message import EmailMessage
from app.core.config import settings
from app.core.logger import logger


def _build_otp_message(to_email: str, otp_code: str) -> EmailMessage:
    sender = settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to_email
    message["Subject"] = "Your MedMemory verification code"
    message.set_content(
        f"Your MedMemory email verification code is {otp_code}.\n\n"
        f"This code expires in {settings.OTP_EXPIRE_MINUTES} minutes.\n"
        "If you did not request this code, you can ignore this email."
    )
    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>MedMemory Verification Code</title>
</head>
<body style="margin:0;padding:0;background-color:#f2f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1e293b;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#f2f6f8;padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:480px;background-color:#ffffff;border-radius:10px;border:1px solid #dbe5ea;overflow:hidden;">
          <tr>
            <td style="background-color:#0f766e;padding:20px 24px;">
              <div style="font-size:18px;font-weight:700;color:#ffffff;letter-spacing:0.2px;">MedMemory</div>
              <div style="font-size:12px;color:#ccfbf1;margin-top:2px;">Personal Health Records &amp; Clinical Timeline</div>
            </td>
          </tr>
          <tr>
            <td style="padding:28px 24px;">
              <p style="margin:0 0 12px;font-size:15px;line-height:1.5;color:#1e293b;">
                Use the verification code below to verify your MedMemory account:
              </p>
              <div style="margin:20px 0;padding:16px;text-align:center;background-color:#f0fdfa;border:1px solid #99f6e4;border-radius:8px;">
                <span style="font-size:28px;font-weight:700;letter-spacing:6px;color:#0f766e;font-family:monospace;">{otp_code}</span>
              </div>
              <p style="margin:0 0 10px;font-size:13px;line-height:1.5;color:#475569;">
                This code expires in <strong>{settings.OTP_EXPIRE_MINUTES} minutes</strong>.
              </p>
              <p style="margin:0;font-size:13px;line-height:1.5;color:#64748b;">
                If you did not request this code, please ignore this email—your health records remain secure.
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 24px;background-color:#f8fafc;border-top:1px solid #e2e8f0;font-size:12px;color:#64748b;line-height:1.4;">
              MedMemory &bull; Sent automatically for account security.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    message.add_alternative(html_body, subtype="html")
    return message


def _deliver_smtp(to_email: str, otp_code: str) -> None:
    message = _build_otp_message(to_email, otp_code)
    if settings.SMTP_USE_TLS:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
            server.starttls()
            if settings.SMTP_USERNAME:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(message)
        return

    with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
        if settings.SMTP_USERNAME:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(message)


async def send_otp_email(to_email: str, otp_code: str) -> None:
    """Delivers the OTP over SMTP, or logs it locally when mail is unset in development."""
    if not settings.SMTP_HOST:
        if "dev" in settings.ENV.lower():
            logger.info(f"[Auth OTP] SMTP unconfigured in development; OTP dispatched to logs for {to_email}: {otp_code}")
            return
        raise RuntimeError("Email delivery is not configured.")

    try:
        await asyncio.to_thread(_deliver_smtp, to_email, otp_code)
        logger.info(f"[Auth OTP] Verification email dispatched to {to_email}")
    except Exception as exc:
        logger.error(f"[Auth OTP] Failed to dispatch verification email to {to_email}: {exc}", exc_info=True)
        raise RuntimeError("Unable to send verification email.") from exc
