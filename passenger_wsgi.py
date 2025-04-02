import sys, os
INTERP = os.path.expanduser("/home/teampack/virtualenv/home/teampack/public_html/3.9/bin/python")
if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)
sys.path.append(os.getcwd())
from wsgi import app as application