from job_agent.answers import DECLINE, RESUME, Answerer, Resolution, choose_option
from job_agent.models import FormField, Job

JOB = Job(
    source="greenhouse", company="Anthropic", title="Research Engineer", location="SF", url="u"
)


def ask(
    answerer: Answerer,
    label: str,
    kind: str = "select",
    options: tuple[str, ...] = ("Yes", "No"),
    required: bool = True,
    key: str = "question_1",
    section: str = "custom",
    description: str = "",
    job: Job = JOB,
) -> Resolution:
    field = FormField(key, label, kind, required, list(options), section, description)
    return answerer.resolve(field, job)


def test_sponsorship_family(answerer: Answerer) -> None:
    assert ask(answerer, "Do you require visa sponsorship? ").value == "Yes"
    long_form = (
        "Will you now or will you in the future require employment visa sponsorship to work in "
        "the country in which the job you're applying for is located?"
    )
    assert ask(answerer, long_form).value == "Yes"
    assert ask(answerer, "Are you legally authorized to work in the United States?").value == "Yes"
    assert (
        ask(answerer, "Are you authorized to work in the U.S. without sponsorship?").value == "No"
    )
    no_need = "Can you work in the US without the need for visa sponsorship now or in the future?"
    assert ask(answerer, no_need).value == "No"
    typo = "Do you, now or in the future, require sponorship to work in the country you reside?"
    assert ask(answerer, typo, kind="boolean", options=()).value is True


def test_office_days(answerer: Answerer) -> None:
    quarter = "Are you open to working in-person in one of our offices 25% of the time?"
    assert ask(answerer, quarter).value == "Yes"
    assert ask(answerer, "The role is in the office 3 days a week. Are you able to?").value == "Yes"
    assert (
        ask(answerer, "The role is in the office 5 days a week. Are you able to?").status
        == "unknown"
    )


def test_attestations_wait_for_a_decision(answerer: Answerer) -> None:
    policy = ask(
        answerer,
        "AI Policy for Application",
        description="Review our AI partnership guidelines for candidates and confirm",
    )
    assert policy.status == "blocked"
    personal = ask(answerer, "I confirm I personally completed this application", "boolean", ())
    assert personal.status == "blocked"
    assert ask(answerer, "Do you agree to the arbitration agreement?").status == "blocked"
    technical = ask(answerer, "Describe your experience with large language models", "textarea", ())
    assert technical.status == "unknown"


def test_standard_and_computed(answerer: Answerer) -> None:
    first = ask(answerer, "First Name", "text", (), key="first_name", section="standard")
    assert first.value == "Alex"
    resume = ask(answerer, "Resume/CV", "file", (), key="resume", section="standard")
    assert resume.value == RESUME
    linkedin = ask(answerer, "LinkedIn Profile", "text", (), required=False)
    assert linkedin.value.startswith("https://www.linkedin.com/")
    start = "When is the earliest you would want to start working with us?"
    assert ask(answerer, start, "text", (), required=False).value == "11/06/2026"
    heard = ("LinkedIn", "Referral", "Company Website", "Other")
    assert (
        ask(answerer, "How did you hear about this job?", options=heard).value == "Company Website"
    )
    found_on_linkedin = Job(
        source="greenhouse",
        company="Anthropic",
        title="x",
        location="SF",
        url="u",
        linkedin_id="42",
    )
    via = ask(
        answerer, "How did you hear about us?", options=("LinkedIn", "Other"), job=found_on_linkedin
    )
    assert via.value == "LinkedIn"
    assert ask(answerer, "Have you previously worked for Anthropic?").value == "No"
    assert ask(answerer, "Are you at least 18 years of age?").value == "Yes"
    assert ask(answerer, "Have you ever interviewed at Anthropic before?").status == "unknown"
    assert ask(answerer, "Are you open to relocation for this role?").status == "unknown"


def test_eeo(answerer: Answerer) -> None:
    gender = ask(
        answerer,
        "Gender",
        options=("Male", "Female", "Decline To Self Identify"),
        key="gender",
        section="eeo",
        required=False,
    )
    assert gender.value == "Male"
    identity = ask(
        answerer,
        "Gender identity",
        options=("Woman", "Man", "Non-binary", "I don't wish to answer"),
        section="eeo",
        required=False,
    )
    assert identity.value == "Man"
    veteran = ask(
        answerer,
        "veteran",
        options=("I am a veteran", "I am not a veteran", "Decline to self-identify"),
        key="eeo[veteran]",
        section="eeo",
        required=False,
    )
    assert veteran.value == "I am not a veteran"
    race = ask(
        answerer,
        "Race",
        options=("Asian", "White", "Decline To Self Identify"),
        key="race",
        section="eeo",
        required=False,
    )
    assert race.value == "Decline To Self Identify"
    disability = ask(
        answerer,
        "DisabilityStatus",
        options=(
            "Yes, I have a disability, or have had one in the past",
            "No, I do not have a disability and have not had one in the past",
            "I do not want to answer",
        ),
        key="disability_status",
        section="eeo",
        required=False,
    )
    assert disability.value == "I do not want to answer"


def test_choose_option() -> None:
    assert choose_option("Male", ["Female", "Male"]) == "Male"
    sponsor = ["Yes, I will require sponsorship", "No, I will not"]
    assert choose_option("Yes", sponsor) == "Yes, I will require sponsorship"
    assert choose_option("No", ["Yes ", "No "]) == "No "
    assert (
        choose_option(DECLINE, ["Yes", "No", "I don't wish to answer"]) == "I don't wish to answer"
    )
    assert choose_option("5+", ["0-2", "3-5", "6-10"]) is None


def test_privacy_and_accuracy_acknowledgements(answerer: Answerer) -> None:
    reddit = (
        'By selecting "I agree," I understand that the information I have provided will be '
        "processed in accordance with Reddit's Candidate Privacy Policy."
    )
    assert ask(answerer, reddit, options=("I agree",)).value == "I agree"
    vercel = "By submitting, I acknowledge Vercel's Job Applicant Privacy Notice"
    assert ask(answerer, vercel, options=("Acknowledge/Confirm",)).value == "Acknowledge/Confirm"
    okta = "I acknowledge and agree to the processing of my personal data per Okta's privacy policy"
    assert ask(answerer, okta, "multiselect", ("I acknowledge",)).value == ["I acknowledge"]
    accuracy = (
        "Please double-check all the information provided above. Ensuring accuracy is crucial."
    )
    reviewed = ("I have reviewed and confirmed that all the information provided is accurate.",)
    assert ask(answerer, accuracy, options=reviewed).value == reviewed[0]


def test_more_standard_facts(answerer: Answerer) -> None:
    company = "Please provide the name of your current (or most recent) company"
    assert ask(answerer, company, "text", ()).value == "ExampleCorp"
    assert ask(answerer, "Current/Last Company", "text", ()).value == "ExampleCorp"
    assert ask(answerer, "Where have you most recently worked?", "text", ()).value == "ExampleCorp"
    legal = "Please provide your full legal name as it appears on your government ID"
    assert ask(answerer, legal, "text", ()).value == "Alex Example"
    countries = ("Canada", "United States of America", "Mexico")
    assert ask(answerer, "Country", options=countries).value == "United States of America"
    states = ("Arizona", "California", "Not in the US")
    assert (
        ask(answerer, "Please select your current state of residence.", options=states).value
        == "California"
    )
    small = "Do you live in one of the following states? Alabama, Alaska, Delaware, or Wyoming."
    assert ask(answerer, small).value == "No"
    okta = Job(source="greenhouse", company="Okta", title="x", location="SF", url="u")
    employed = "Have you been employed by Okta, Inc. or any of its subsidiaries in the past?"
    assert ask(answerer, employed, job=okta).value == "No"
    heard = ("Events", "LinkedIn", "Google Search", "Other job boards", "Other")
    assert (
        ask(answerer, "Where did you first hear about this role?", options=heard).value == "Other"
    )


def test_descriptive_work_authorization(answerer: Answerer) -> None:
    waymo = (
        "I am authorized to work for any employer in the country in which this position is based.",
        "I require, or in the future will require, Waymo's sponsorship to obtain authorization.",
    )
    assert ask(answerer, "Work Authorization", options=waymo).value == waymo[1]
    permit = (
        "I am authorized to work in the country due to my nationality",
        "I am authorized to work in the country based on a valid work permit/visa",
        "I am not authorized to work in the country",
    )
    label = "Your authorization to work in the country where you live."
    assert ask(answerer, label, options=permit).value == permit[1]
    two_yes = (
        "Yes, I will require immigration sponsorship now",
        "Yes, I will require immigration sponsorship in the future",
        "No",
    )
    future = (
        "Will you now or in the future require company sponsorship to retain your authorization?"
    )
    assert ask(answerer, future, options=two_yes).status == "unknown"


def test_more_eeo_wordings(answerer: Answerer) -> None:
    military = ("Active Reserve", "Retired", "No military service", "Decline to answer")
    veteran = ask(answerer, "Are you a veteran/have you served in the military?", options=military)
    assert veteran.value == "No military service"
    identity = ("Cisgender", "Transgender", "I prefer to self-describe", "I don't wish to answer")
    chosen = ask(answerer, "I identify as:", options=identity, section="eeo", required=False)
    assert chosen.value == "I don't wish to answer"
    lgbt = ask(
        answerer,
        "Do you consider yourself a member of the LGBTQIA+ community?",
        "multiselect",
        ("Yes", "No", "I don't wish to answer"),
        section="eeo",
        required=False,
    )
    assert lgbt.value == ["I don't wish to answer"]
