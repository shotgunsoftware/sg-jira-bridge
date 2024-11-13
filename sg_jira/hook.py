

class JiraHook(object):

    def __init__(self, bridge, logger):
        """Class constructor"""
        super(JiraHook, self).__init__()
        self._bridge = bridge
        self._logger = logger

    @property
    def bridge(self):
        return self._bridge

    @property
    def shotgun(self):
        return self._bridge.shotgun

    @property
    def jira(self):
        return self._bridge.jira
