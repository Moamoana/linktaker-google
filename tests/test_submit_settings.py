"""Setelan pengiriman: default kode, ditimpa environment, ditimpa flag."""

import os

from linktaker import config
from linktaker.submit.settings import Settings


def test_default_mengikuti_config():
    s = Settings.from_env(env={})

    assert s.url == config.SUBMIT_URL
    assert s.batch_size == config.SUBMIT_BATCH_SIZE == 100


def test_environment_menimpa_default():
    s = Settings.from_env(env={
        "SUBMIT_URL": "http://lain/submit_batch/",
        "SUBMIT_BATCH_SIZE": "50",
        "SUBMIT_TIMEOUT": "5.5",
    })

    assert s.url == "http://lain/submit_batch/"
    assert s.batch_size == 50
    assert s.timeout == 5.5


def test_nilai_kosong_diperlakukan_sebagai_tidak_diisi():
    """Script shell meneruskan variabel yang belum diset sebagai string kosong;
    int("") tidak boleh menggagalkan run yang sebenarnya baik-baik saja."""
    s = Settings.from_env(env={"SUBMIT_BATCH_SIZE": "", "SUBMIT_RETRIES": "   "})

    assert s.batch_size == config.SUBMIT_BATCH_SIZE
    assert s.retries == config.SUBMIT_RETRIES


def test_nilai_ngawur_jatuh_ke_default():
    s = Settings.from_env(env={"SUBMIT_BATCH_SIZE": "banyak"})

    assert s.batch_size == config.SUBMIT_BATCH_SIZE


def test_lokasi_file_state_ikut_state_dir():
    s = Settings.from_env(env={"SUBMIT_STATE_DIR": os.path.join("data", "state")})

    assert s.sent_file == os.path.join("data", "state", "sent-urls.txt")
    assert s.queue_file == os.path.join("data", "state", "pending-urls.txt")
