from datetime import datetime

from pkg_resources import get_distribution
import stsci_rtd_theme


def setup(app):
    app.add_stylesheet("stsci.css")


project = "jirahub"
copyright = f"{datetime.now().year}, STScI"
author = "STScI"
release = get_distribution("jirahub").version
html_theme = "stsci_rtd_theme"
html_theme_path = [stsci_rtd_theme.get_html_theme_path()]
html_static_path = ["_static"]
html_context = {"css_files": ["_static/theme_overrides.css"]}  # override wide tables in RTD theme
