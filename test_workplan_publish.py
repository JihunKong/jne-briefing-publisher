import json
import re
import subprocess
import unittest

from workplan_publish import TEMPLATE, render_html


class MonthRenderingTests(unittest.TestCase):
    def render_both(self, month):
        payload = {"ok": True, "months": [month]}
        server = render_html(payload, "", "test")
        script = re.search(r"<script>(.*?)</script>", TEMPLATE, re.S).group(1)
        script = script.replace("__DATA_JSON__", json.dumps(payload)).replace("__API_URL__", "")
        script = """
var document = {createElement: function() {return {
  textContent: '',
  get innerHTML() {return this.textContent.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');}
};}};
""" + script
        script += "\nconsole.log(monthCard(DATA.months[0])); console.log(JSON.stringify(deptSource()));"
        browser = subprocess.run(["node"], input=script, capture_output=True, text=True)
        self.assertEqual(browser.returncode, 0, browser.stderr)
        return server, browser.stdout

    def test_calendar_payload_keeps_events_and_escapes_html(self):
        month = {"label": "2026-09", "weeks": [[
            {"d": 0}, {"d": 14, "iso": "2026-09-14", "items": ["Meeting <test>"]}
        ]], "notes": "Reminder"}
        for rendered in self.render_both(month):
            self.assertIn("Meeting &lt;test&gt;", rendered)
            self.assertIn("Reminder", rendered)
            self.assertIn("2026-09", rendered)

    def test_legacy_department_payload(self):
        month = {"label": "2026-09", "weekRanges": ["9/14-9/20"],
                 "depts": [{"name": "Office", "weeks": ["Planning"]}]}
        for rendered in self.render_both(month):
            self.assertIn("Planning", rendered)
            self.assertIn("9/14-9/20", rendered)

    def test_missing_calendar_tab_and_no_department_list(self):
        for rendered in self.render_both({"label": "2026-10"}):
            self.assertIn("2026-10", rendered)


if __name__ == "__main__":
    unittest.main()
