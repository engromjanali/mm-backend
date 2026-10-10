from django.db import migrations

PRIVACY_POLICY = """We respect your privacy and only collect the information needed to manage mess membership, meals, deposits, costs, funds, notices and account access.

# Information we collect
- Account details such as name, email, phone number and profile photo.
- Mess, season and membership details, including role and membership status.
- Meal, deposit, cost, fund, notice and opinion records created inside the app.
- Basic device, language and authentication data required to keep your session secure.

# How we use information
- To show your current mess, season, balance, meal history and member status.
- To allow managers to record meals, deposits, costs, funds, notices and membership actions.
- To secure accounts, prevent unauthorized access and keep app data accurate.
- To improve reliability, performance and the overall user experience.

# Sharing and access
- Your mess data is visible only to authorized members or managers based on role.
- We do not sell your personal information.
- Data may be shared when required by law, safety needs or legitimate service operation.

# Data security
- Authentication tokens are used to protect private API requests.
- Access is role-based, so members and managers only see permitted actions.
- No system is perfectly secure, but we use reasonable safeguards to protect your data.

# Your choices
- You can update account and mess details where the app allows.
- You can sign out any time from your profile.
- You can request deletion of your account from your profile. It is deleted 60 days later unless you sign in and cancel.

# Contact
For privacy questions, contact the app administrator or your mess manager."""

TERMS = """By creating an account or using the app you agree to these terms.

# Your account
- Keep your password private; you are responsible for activity on your account.
- Use your real name and contact details so your mess can recognise you.

# Using the app
- Record meals, deposits and costs honestly; managers can correct records in their mess.
- Don't misuse the app, try to access other messes' data or disrupt the service.

# Managers
- The manager and acting manager can add, edit and delete records for their mess.
- Managers are responsible for keeping their mess's records accurate.

# Changes and availability
- We may update the app and these terms; continued use means you accept the changes.
- The app may be unavailable during maintenance.

# Ending your account
You can request deletion of your account from your profile. It is deleted 60 days later unless you sign in and cancel."""

FAQS = [
    ("How do I join a mess?", "Ask the mess manager for an invitation, or find the mess under Join mess and send a join request. Invitations and requests expire after 7 days."),
    ("What is a season?", "A season is the period meals, deposits and costs are counted in, usually a month. A mess can run several seasons; switch between them from Membership."),
    ("How is my balance calculated?", "Your deposits minus your share of the season's costs, based on how many meals you had."),
    ("Who can add meals, deposits and costs?", "The mess manager and acting manager. Members can see their own records."),
    ("How do I delete my account?", "Go to Profile → Delete account. Your account is deleted 60 days later; sign in before then to cancel."),
]


def add_default_content(apps, schema_editor):
    AppSetting = apps.get_model('ContentManagement', 'AppSetting')
    ContentPage = apps.get_model('ContentManagement', 'ContentPage')
    Faq = apps.get_model('ContentManagement', 'Faq')
    AppSetting.objects.get_or_create(pk=1)
    ContentPage.objects.get_or_create(kind='privacy-policy', language='en', defaults={'title': 'Privacy policy', 'body': PRIVACY_POLICY})
    ContentPage.objects.get_or_create(kind='terms-and-conditions', language='en', defaults={'title': 'Terms and conditions', 'body': TERMS})
    if not Faq.objects.exists():
        Faq.objects.bulk_create([Faq(language='en', question=q, answer=a, order=i) for i, (q, a) in enumerate(FAQS)])


class Migration(migrations.Migration):

    dependencies = [
        ('ContentManagement', '0001_app_settings_pages_and_faqs'),
    ]

    operations = [
        migrations.RunPython(add_default_content, migrations.RunPython.noop),
    ]
