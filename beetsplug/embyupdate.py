# -*- coding: utf-8 -*-

"""Updates the Emby Library whenever the beets library is changed.

    emby:
        host: localhost
        port: 8096
        username: user
        password: password
"""
from __future__ import division, absolute_import, print_function

import hashlib
import requests

from six.moves.urllib.parse import urlencode
from six.moves.urllib.parse import urljoin, parse_qs, urlsplit, urlunsplit

from beets import config
from beets.plugins import BeetsPlugin


def api_url(host, port, endpoint):
    """Returns a joined url.

    Takes host, port and endpoint and generates a valid emby API url.

    :param host: Hostname of the emby server
    :param port: Portnumber of the emby server
    :param endpoint: API endpoint
    :type host: str
    :type port: int
    :type endpoint: str
    :returns: Full API url
    :rtype: str
    """
    # check if http or https is defined as host and create hostname
    hostname_list = [host]
    if host.startswith('http://') or host.startswith('https://'):
        hostname = ''.join(hostname_list)
    else:
        hostname_list.insert(0, 'http://')
        hostname = ''.join(hostname_list)

    joined = urljoin(
        '{hostname}:{port}'.format(
            hostname=hostname,
            port=port
        ),
        endpoint
    )

    scheme, netloc, path, query_string, fragment = urlsplit(joined)
    query_params = parse_qs(query_string)

    query_params['format'] = ['json']
    new_query_string = urlencode(query_params, doseq=True)

    return urlunsplit((scheme, netloc, path, new_query_string, fragment))


def password_data(username, password):
    """Returns a dict with username and its encoded password.

    :param username: Emby username
    :param password: Emby password
    :type username: str
    :type password: str
    :returns: Dictionary with username and encoded password
    :rtype: dict
    """
    return {
        'username': username,
        'password': hashlib.sha1(password.encode('utf-8')).hexdigest(),
        'passwordMd5': hashlib.md5(password.encode('utf-8')).hexdigest()
    }


def create_headers(user_id, token=None):
    """Return header dict that is needed to talk to the Emby API.

    :param user_id: Emby user ID
    :param token: Authentication token for Emby
    :type user_id: str
    :type token: str
    :returns: Headers for requests
    :rtype: dict
    """
    headers = {}

    authorization = (
        'MediaBrowser UserId="{user_id}", '
        'Client="other", '
        'Device="beets", '
        'DeviceId="beets", '
        'Version="0.0.0"'
    ).format(user_id=user_id)

    headers['x-emby-authorization'] = authorization

    if token:
        headers['x-mediabrowser-token'] = token

    return headers


def get_token(host, port, headers, auth_data):
    """Return token for a user.

    :param host: Emby host
    :param port: Emby port
    :param headers: Headers for requests
    :param auth_data: Username and encoded password for authentication
    :type host: str
    :type port: int
    :type headers: dict
    :type auth_data: dict
    :returns: Access Token
    :rtype: str
    """
    url = api_url(host, port, '/Users/AuthenticateByName')
    r = requests.post(url, headers=headers, data=auth_data)

    return r.json().get('AccessToken')


def get_user(host, port, username):
    """Return user dict from server or None if there is no user.

    :param host: Emby host
    :param port: Emby port
    :username: Username
    :type host: str
    :type port: int
    :type username: str
    :returns: Matched Users
    :rtype: list
    """
    url = api_url(host, port, '/Users/Public')
    r = requests.get(url)
    user = [i for i in r.json() if i['Name'] == username]

    return user


class EmbyUpdate(BeetsPlugin):
    def __init__(self):
        super(EmbyUpdate, self).__init__()

        # Adding defaults.
        config['emby'].add({
            u'host': u'http://localhost',
            u'port': 8096
        })

        self.register_listener('database_change', self.listen_for_db_change)

    def listen_for_db_change(self, lib, model):
        """Listens for beets db change and register the update for the end.
        """
        self.register_listener('cli_exit', self.update)

    def update(self, lib):
        """When the client exists try to send refresh request to Emby.
        """
        self._log.info(u'Updating Emby library...')

        host = config['emby']['host'].get()
        port = config['emby']['port'].get()
        username = config['emby']['username'].get()
        password = config['emby']['password'].get()
        token = config['emby']['apikey'].get()

        # Get user information from the Emby API.
        user = get_user(host, port, username)
        if not user:
            self._log.warning(u'User {0} could not be found.'.format(username))
            return

        if not token:
            # Create Authentication data and headers.
            auth_data = password_data(username, password)
            headers = create_headers(user[0]['Id'])

            # Get authentication token.
            token = get_token(host, port, headers, auth_data)
            if not token:
                self._log.warning(
                    u'Could not get token for user {0}', username
                )
                return

        # Recreate headers with a token.
        headers = create_headers(user[0]['Id'], token=token)

        # Trigger the Update.
        url = api_url(host, port, '/Library/Refresh')
        r = requests.post(url, headers=headers)
        if r.status_code != 204:
            self._log.warning(u'Update could not be triggered')
        else:
            self._log.info(u'Update triggered.')
