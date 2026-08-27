import ssl

from smtpweb.smtp.tls import build_tls_context, ensure_self_signed_cert


def test_ensure_self_signed_cert_creates_files(tmp_path):
    cert_dir = tmp_path / "tls"
    cert_path, key_path = ensure_self_signed_cert(cert_dir)
    assert cert_path.exists()
    assert key_path.exists()
    assert cert_path.read_bytes().startswith(b"-----BEGIN CERTIFICATE-----")


def test_ensure_self_signed_cert_reuses_existing(tmp_path):
    cert_dir = tmp_path / "tls"
    cert_path, key_path = ensure_self_signed_cert(cert_dir)
    first_cert_bytes = cert_path.read_bytes()
    first_key_bytes = key_path.read_bytes()

    cert_path2, key_path2 = ensure_self_signed_cert(cert_dir)
    assert cert_path2.read_bytes() == first_cert_bytes
    assert key_path2.read_bytes() == first_key_bytes


def test_key_file_is_not_world_readable(tmp_path):
    cert_dir = tmp_path / "tls"
    _, key_path = ensure_self_signed_cert(cert_dir)
    mode = key_path.stat().st_mode & 0o777
    assert mode & 0o077 == 0, f"key file permissions too open: {oct(mode)}"


def test_build_tls_context_loads_successfully(tmp_path):
    cert_path, key_path = ensure_self_signed_cert(tmp_path / "tls")
    context = build_tls_context(cert_path, key_path)
    assert isinstance(context, ssl.SSLContext)
