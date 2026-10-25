from job_agent.models import Job
from job_agent.sources import greenhouse, lever

LEVER = """<form id="application-form"><ul>
<li class="application-question"><label><div class="application-label">Resume/CV
<span class="required">*</span></div><input type="file" name="resume"></label></li>
<li class="application-question"><label><div class="application-label">Full name
<span class="required">*</span></div><input type="text" name="name"></label></li>
<li class="application-question"><label><div class="application-label">Phone</div>
<input type="text" name="phone"></label></li></ul>
<input type="hidden" name="cards[abc-123][baseTemplate]" value='{"text": "Questions", "fields":
[{"type": "multiple-choice", "text": "Do you require sponsorship?", "required": true,
"options": [{"text": "Yes"}, {"text": "No"}]}]}'>
<select name="eeo[gender]"><option value="">Select</option><option value="Male">Male</option>
<option value="Female">Female</option></select>
<div class="h-captcha" data-sitekey="x"></div></form>"""


def _job(ats: str) -> Job:
    return Job(ats, "Acme", "t", "SF", "u", ats=ats, ats_slug="acme", ats_job_id="1")


def test_greenhouse_fields() -> None:
    job = _job("greenhouse")
    select = {
        "name": "question_1",
        "type": "multi_value_single_select",
        "values": [{"label": "Yes", "value": 1}, {"label": "No", "value": 0}],
    }
    veteran = {
        "name": "veteran_status",
        "type": "multi_value_single_select",
        "values": [{"label": "I am not a protected veteran", "value": "1"}],
    }
    job.raw["detail"] = {
        "questions": [
            {
                "label": "Resume/CV",
                "required": True,
                "fields": [
                    {"name": "resume", "type": "input_file"},
                    {"name": "resume_text", "type": "textarea"},
                ],
            },
            {"label": "Do you require visa sponsorship?", "required": True, "fields": [select]},
        ],
        "compliance": [
            {
                "type": "eeoc",
                "questions": [
                    {"label": "VeteranStatus", "required": False, "fields": [veteran]},
                ],
            }
        ],
        "data_compliance": [{"type": "gdpr", "requires_consent": True}],
    }
    fields = greenhouse.form_fields(job)
    assert [(f.key, f.kind, f.section) for f in fields] == [
        ("resume", "file", "standard"),
        ("question_1", "select", "custom"),
        ("veteran_status", "select", "eeo"),
        ("consent_gdpr", "boolean", "consent"),
    ]


def test_lever_form() -> None:
    job = _job("lever")
    fields = {f.key: f for f in lever.parse_form(LEVER, job)}
    assert fields["resume"].required and fields["name"].required
    assert not fields["phone"].required
    question = fields["cards[abc-123][field0]"]
    assert question.kind == "select" and question.required and question.options == ["Yes", "No"]
    assert fields["eeo[gender]"].options == ["Male", "Female"]
    assert job.raw["captcha"] == "hCaptcha"
