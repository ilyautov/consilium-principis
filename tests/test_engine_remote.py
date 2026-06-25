import os, sys, pytest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))   # ТОЛЬКО scripts/
from engine.remote import RemoteEngine


def test_unconfigured_raises_clearly():
    with pytest.raises(NotImplementedError) as e:
        RemoteEngine(endpoint=None, token=None).retrieve("q", "/tmp/adv")
    assert "remote" in str(e.value).lower()

def test_available_false_when_unconfigured():
    assert RemoteEngine.available(endpoint=None) is False
