# -*- coding: utf-8 -*-
"""
Copyright (C) 2026 BookBanana
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import requests, json, time

class GithubAPI:
    def __init__(self, token=None):
        self.token = token

    def setToken(self, token_):
        self.token = token_

    def checkConnection(self,lambda:lamb):
        try:
            start = time.perf_counter()
            resp = requests.get(
                "https://api.github.com/",
                headers={"Authorization": f"token {self.token}"},
                timeout=5
            )
            latency = int((time.perf_counter() - start) * 1000) 

            if resp.status_code == 200:
                return latency
            else:
                return abs(resp.status_code) * -1

        except requests.exceptions.Timeout:
            return -2
        except requests.exceptions.ConnectionError:
            return -3
        except requests.exceptions.SSLError:
            return -4
        except:
            return -99

    @classmethod
    def checkToken(self, token_= None):
        if token_ is None:
            try:
                token_ = self.token
            except:
                return False, None
        url = "https://api.github.com/user"
        headers = {
            "Authorization": f"token {token_}",
            "Accept": "application/vnd.github.v3+json",
        }
        
        try:
            rest = requests.get(url, headers=headers, timeout=10)

            if rest.status_code == 200:
                return True, {"body":rest.json(),"head":rest.headers}
            elif rest.status_code == 401:
                return False, "Invalid token"
            elif rest.status_code == 403:
                return False, "Tonen Refused"
            else:
                return False, rest.status_code
        except requests.ConnectionError:
            return False, "ConnectionError"
        except Exception as e:
            return False, e

    def search(self, query, page=1):
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {self.token}"
        }
        url = "https://api.github.com/search/repositories"
        try:
            params = {
                "q": query,
                "page": page,
                "per_page": 50,
                "sort": "stars",
                "order": "desc"
            }

            rest = requests.get(url, headers=headers, params=params)
            return True, rest.json()
        except Exception:
            return False, None

    def getRepo(self, repo):
        url = f"https://api.github.com/repos/{repo}"
        headers = {
            "Authorization": f"token {self.token}"
        }
        try :
            rest = requests.get(url, headers=headers)
            if rest.status_code == 200:
                return True, rest.json()
            else:
                return False, rest.status_code
        except Exception:
            return False, None

    def getRelease(self,repo):
        url = f"https://api.github.com/repos/{repo}/releases"
        headers = {
            "Authorization": f"token {self.token}"
        }
        try :
            params = {
                "page": page,
                "per_page": 50
            }

            rest = requests.get(url, headers=headers)
            if rest.status_code == 200:
                return True, rest.json()
            else:
                return False, rest.status_code
        except Exception:
            return False, None
    