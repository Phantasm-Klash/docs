# gotouhou Ops Helpers

## Hourly progress mail

`hourly_progress_mail.py` sends a multi-repository summary to `wjcwqc@qq.com`
through `smtp.ym.163.com:25`. It reads SMTP credentials from environment
variables and does not store secrets in git.

Dry run:

```sh
python3 ops/hourly_progress_mail.py --dry-run
```

Systemd setup on the development host:

```sh
sudo install -d -m 0750 /etc/gotouhou
sudo install -m 0644 ops/gotouhou-hourly-progress.service /etc/systemd/system/
sudo install -m 0644 ops/gotouhou-hourly-progress.timer /etc/systemd/system/
sudo editor /etc/gotouhou/progress-mail.env
sudo systemctl daemon-reload
sudo systemctl enable --now gotouhou-hourly-progress.timer
```

Example `/etc/gotouhou/progress-mail.env`:

```sh
GOTOUHOU_SMTP_HOST=smtp.ym.163.com
GOTOUHOU_SMTP_PORT=25
GOTOUHOU_SMTP_USER=example@ym.163.com
GOTOUHOU_SMTP_PASSWORD=replace-with-mail-authorization-code
GOTOUHOU_MAIL_FROM=example@ym.163.com
GOTOUHOU_MAIL_TO=wjcwqc@qq.com
```

Use `GOTOUHOU_SMTP_STARTTLS=1` only if the target SMTP account supports STARTTLS
on the configured port.
