"""
app.py  —  Streamlit Cloud entry point
---------------------------------------
Set Main file path = "app.py" in Streamlit Cloud settings.
This file sets up Python paths then runs dashboard/app.py.
"""
import runpy, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
for p in [ROOT, os.path.join(ROOT, "dashboard")]:
    if p not in sys.path:
        sys.path.insert(0, p)

runpy.run_path(os.path.join(ROOT, "dashboard", "app.py"), run_name="__main__")
