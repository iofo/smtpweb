import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    smtp_host: str = os.environ.get("SMTPWEB_SMTP_HOST", "0.0.0.0")
    smtp_port: int = int(os.environ.get("SMTPWEB_SMTP_PORT", "1025"))
    web_host: str = os.environ.get("SMTPWEB_WEB_HOST", "0.0.0.0")
    web_port: int = int(os.environ.get("SMTPWEB_WEB_PORT", "8080"))
    data_dir: Path = Path(os.environ.get("SMTPWEB_DATA_DIR", "./data/emails"))
