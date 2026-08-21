"""FIRE - FIkspunktREgister"""
print("importerede fire.__init__")
from uuid import uuid4

__version__ = "1.10.0"
__license__ = "MIT"
__author__ = "SDFI, Septima"
__author_email__ = "grf@sdfi.dk"


def uuid():
    """UUID generator"""
    return str(uuid4())
