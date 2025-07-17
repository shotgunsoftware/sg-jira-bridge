from sg_jira import JiraHook


class CustomJiraHook(JiraHook):

    def format_sg_date(self, jira_date):
        return "fixture_date"
