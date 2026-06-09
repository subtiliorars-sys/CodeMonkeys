#!/usr/bin/env python3
"""
🐙 GitHub Bridge — Unit Tests
===============================
Tests for github_bridge.py. Uses only stdlib + unittest.mock.
Zero real network calls — all external requests are mocked.
"""

import json
import sys
import os
import unittest
from unittest.mock import MagicMock, patch, mock_open

# Ensure the workspace is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Test Token Validation ──────────────────────────────────────

class TestTokenValidation(unittest.TestCase):
    """Tests for validate_token()"""

    def setUp(self):
        from github_bridge import validate_token
        self.validate = validate_token

    def test_empty_token(self):
        result = self.validate("")
        self.assertFalse(result.get("valid"))
        self.assertIn("empty", result.get("error", "").lower())

    def test_whitespace_token(self):
        result = self.validate("   ")
        self.assertFalse(result.get("valid"))
        self.assertIn("empty", result.get("error", "").lower())

    @patch("github_bridge._github_api_get")
    def test_valid_token(self, mock_get):
        mock_get.return_value = {
            "data": {
                "login": "testuser",
                "name": "Test User",
                "avatar_url": "https://avatars.github.com/u/1",
            },
            "http_status": 200,
            "headers": {
                "X-OAuth-Scopes": "repo, workflow",
                "X-RateLimit-Remaining": "5000",
            },
            "error": None,
        }
        result = self.validate("ghp_valid123")
        self.assertTrue(result.get("valid"))
        self.assertEqual(result.get("user"), "testuser")
        self.assertIn("repo", result.get("scopes", []))
        self.assertEqual(result.get("rate_limit_remaining"), 5000)

    @patch("github_bridge._github_api_get")
    def test_401_unauthorized(self, mock_get):
        mock_get.return_value = {
            "data": {"message": "Bad credentials"},
            "http_status": 401,
            "headers": {},
            "error": "Bad credentials",
        }
        result = self.validate("ghp_bad")
        self.assertFalse(result.get("valid"))
        self.assertIn("Invalid token", result.get("error", ""))

    @patch("github_bridge._github_api_get")
    def test_403_forbidden(self, mock_get):
        mock_get.return_value = {
            "data": {"message": "Rate limit exceeded"},
            "http_status": 403,
            "headers": {},
            "error": "Rate limit exceeded",
        }
        result = self.validate("ghp_ratelimited")
        self.assertFalse(result.get("valid"))
        self.assertIn("access denied", result.get("error", "").lower())


# ── Test GitHub API Wrapper ────────────────────────────────────

class TestGithubApiCalls(unittest.TestCase):
    """Tests for _github_api_get and _github_api_post"""

    def setUp(self):
        from github_bridge import _github_api_get, _github_api_post
        self.get = _github_api_get
        self.post = _github_api_post

    @patch("urllib.request.urlopen")
    def test_get_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"login": "testuser"}).encode("utf-8")
        mock_resp.headers = {"X-OAuth-Scopes": "repo"}
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = self.get("/user", "ghp_test")
        self.assertEqual(result.get("http_status"), 200)
        self.assertEqual(result.get("data", {}).get("login"), "testuser")

    @patch("urllib.request.urlopen")
    def test_get_network_error(self, mock_urlopen):
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Connection refused")

        result = self.get("/user", "ghp_test")
        self.assertIn("Network error", result.get("error", ""))

    @patch("urllib.request.urlopen")
    def test_get_http_error(self, mock_urlopen):
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError(
            "https://api.github.com/user", 404,
            "Not Found", {}, None
        )

        result = self.get("/user", "ghp_test")
        self.assertEqual(result.get("http_status"), 404)

    @patch("urllib.request.urlopen")
    def test_post_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 201
        mock_resp.read.return_value = json.dumps({"name": "new-repo"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = self.post("/user/repos", "ghp_test", {"name": "new-repo"})
        self.assertEqual(result.get("http_status"), 201)
        self.assertEqual(result.get("data", {}).get("name"), "new-repo")

    @patch("urllib.request.urlopen")
    def test_post_auth_error(self, mock_urlopen):
        from urllib.error import HTTPError
        error_resp = MagicMock()
        error_resp.code = 401
        error_resp.read.return_value = b'{"message": "Bad credentials"}'
        mock_urlopen.side_effect = HTTPError(
            "https://api.github.com/user/repos", 401,
            "Unauthorized", {}, error_resp
        )

        result = self.post("/user/repos", "ghp_bad", {"name": "test"})
        self.assertEqual(result.get("http_status"), 401)


# ── Test Repo Operations ───────────────────────────────────────

class TestRepoOperations(unittest.TestCase):
    """Tests for list_user_repos, create_repo, list_repo_branches"""

    def setUp(self):
        from github_bridge import list_user_repos, create_repo, list_repo_branches
        self.list_repos = list_user_repos
        self.create_repo = create_repo
        self.list_branches = list_repo_branches

    @patch("github_bridge._github_api_get")
    def test_list_repos_success(self, mock_get):
        mock_get.return_value = {
            "data": [
                {"name": "repo1", "full_name": "user/repo1",
                 "description": "Test repo", "private": False,
                 "fork": False, "language": "Python",
                 "updated_at": "2024-01-01T00:00:00Z",
                 "clone_url": "https://github.com/user/repo1.git",
                 "ssh_url": "git@github.com:user/repo1.git",
                 "default_branch": "main"},
                {"name": "repo2", "full_name": "user/repo2",
                 "description": "Private repo", "private": True,
                 "fork": False, "language": "JavaScript",
                 "updated_at": "2024-01-02T00:00:00Z",
                 "clone_url": "https://github.com/user/repo2.git",
                 "ssh_url": "git@github.com:user/repo2.git",
                 "default_branch": "main"},
            ],
            "http_status": 200,
            "headers": {},
            "error": None,
        }
        result = self.list_repos("ghp_test")
        self.assertIsNone(result.get("error"))
        self.assertEqual(len(result.get("repos", [])), 2)
        self.assertEqual(result["repos"][0]["name"], "repo1")
        self.assertTrue(result["repos"][1]["private"])

    @patch("github_bridge._github_api_get")
    def test_list_repos_failure(self, mock_get):
        mock_get.return_value = {
            "data": {},
            "http_status": 401,
            "headers": {},
            "error": "Bad credentials",
        }
        result = self.list_repos("ghp_bad")
        self.assertIsNotNone(result.get("error"))

    @patch("github_bridge._github_api_get")
    def test_list_branches_success(self, mock_get):
        mock_get.return_value = {
            "data": [
                {"name": "main", "commit": {"sha": "abc123"}},
                {"name": "develop", "commit": {"sha": "def456"}},
            ],
            "http_status": 200,
            "headers": {},
            "error": None,
        }
        result = self.list_branches("ghp_test", "user/repo")
        self.assertIsNone(result.get("error"))
        self.assertEqual(len(result.get("branches", [])), 2)
        self.assertEqual(result["branches"][0]["name"], "main")

    @patch("github_bridge._github_api_post")
    def test_create_repo_success(self, mock_post):
        mock_post.return_value = {
            "data": {
                "name": "new-repo",
                "full_name": "user/new-repo",
                "clone_url": "https://github.com/user/new-repo.git",
                "ssh_url": "git@github.com:user/new-repo.git",
                "html_url": "https://github.com/user/new-repo",
            },
            "http_status": 201,
            "headers": {},
            "error": None,
        }
        result = self.create_repo("ghp_test", "new-repo",
                                  description="A new repo", private=True)
        self.assertIsNone(result.get("error"))
        self.assertEqual(result["repo"]["name"], "new-repo")
        self.assertIn("clone_url", result["repo"])


# ── Test URL Helpers ───────────────────────────────────────────

class TestUrlHelpers(unittest.TestCase):
    """Tests for _embed_token_in_url and _extract_sha"""

    def setUp(self):
        from github_bridge import _embed_token_in_url, _extract_sha
        self.embed = _embed_token_in_url
        self.extract_sha = _extract_sha

    def test_embed_token_in_https_url(self):
        url = "https://github.com/user/repo.git"
        result = self.embed(url, "ghp_test123")
        self.assertIn("x-access-token:ghp_test123@", result)
        self.assertIn("github.com/user/repo.git", result)

    def test_embed_token_already_authenticated(self):
        url = "https://x-access-token:old@github.com/user/repo.git"
        result = self.embed(url, "ghp_new")
        # Should return unchanged since it already has auth
        self.assertEqual(result, url)

    def test_embed_token_ssh_url(self):
        url = "git@github.com:user/repo.git"
        result = self.embed(url, "ghp_test")
        # SSH URLs should not be modified
        self.assertEqual(result, url)

    def test_embed_token_https_no_path(self):
        url = "https://github.com/user"
        result = self.embed(url, "ghp_test")
        self.assertIn("x-access-token:ghp_test@", result)

    def test_extract_sha_found(self):
        output = "[main abc123def456] My commit message"
        result = self.extract_sha(output)
        self.assertEqual(result, "abc123def456")

    def test_extract_sha_not_found(self):
        output = "Everything up-to-date"
        result = self.extract_sha(output)
        self.assertIsNone(result)

    def test_extract_sha_branch_with_slash(self):
        output = "[feature/my-feature abc123def456] Add new thing"
        result = self.extract_sha(output)
        self.assertEqual(result, "abc123def456")


# ── Test Token Storage ─────────────────────────────────────────

class TestTokenStorage(unittest.TestCase):
    """Tests for add_token, get_tokens, get_active_token, delete_token"""

    def setUp(self):
        from github_bridge import (add_token, get_tokens, get_active_token,
                                    delete_token, update_token)
        self.add = add_token
        self.get = get_tokens
        self.active = get_active_token
        self.delete = delete_token
        self.update = update_token

    @patch("github_bridge._get_config_manager")
    def test_add_and_get_token(self, mock_cm):
        mock_cm_instance = MagicMock()
        mock_cm_instance.get_or_create_user.return_value = {
            "github_tokens": []
        }
        mock_cm_instance.load_config.return_value = {
            "users": {"testuser": {"github_tokens": []}}
        }
        mock_cm_instance.save_config.return_value = True
        mock_cm.return_value = mock_cm_instance

        token_obj = self.add("testuser", "My Token", "ghp_test123")
        self.assertIsNotNone(token_obj)
        self.assertEqual(token_obj["name"], "My Token")
        self.assertEqual(token_obj["token"], "ghp_test123")

    @patch("github_bridge._get_config_manager")
    def test_get_tokens_empty(self, mock_cm):
        mock_cm_instance = MagicMock()
        mock_cm_instance.get_user_profile.return_value = {
            "github_tokens": []
        }
        mock_cm.return_value = mock_cm_instance

        tokens = self.get("testuser")
        self.assertEqual(tokens, [])

    @patch("github_bridge._get_config_manager")
    def test_get_tokens_no_profile(self, mock_cm):
        mock_cm_instance = MagicMock()
        mock_cm_instance.get_user_profile.return_value = None
        mock_cm.return_value = mock_cm_instance

        tokens = self.get("nonexistent")
        self.assertEqual(tokens, [])

    @patch("github_bridge._get_config_manager")
    def test_get_active_token_finds_first(self, mock_cm):
        mock_cm_instance = MagicMock()
        mock_cm_instance.get_user_profile.return_value = {
            "github_tokens": [
                {"id": "1", "token": "ghp_first", "is_active": True},
                {"id": "2", "token": "ghp_second", "is_active": True},
            ]
        }
        mock_cm.return_value = mock_cm_instance

        token = self.active("testuser")
        self.assertEqual(token, "ghp_first")

    @patch("github_bridge._get_config_manager")
    def test_get_active_token_none(self, mock_cm):
        mock_cm_instance = MagicMock()
        mock_cm_instance.get_user_profile.return_value = {
            "github_tokens": []
        }
        mock_cm.return_value = mock_cm_instance

        token = self.active("testuser")
        self.assertEqual(token, "")

    @patch("github_bridge._get_config_manager")
    def test_delete_token(self, mock_cm):
        mock_cm_instance = MagicMock()
        mock_cm_instance.get_user_profile.return_value = {
            "github_tokens": [
                {"id": "token1", "name": "First"},
                {"id": "token2", "name": "Second"},
            ]
        }
        mock_cm_instance.load_config.return_value = {
            "users": {"testuser": {"github_tokens": [
                {"id": "token1", "name": "First"},
                {"id": "token2", "name": "Second"},
            ]}}
        }
        mock_cm_instance.save_config.return_value = True
        mock_cm.return_value = mock_cm_instance

        result = self.delete("testuser", "token1")
        self.assertTrue(result)


# ── Test Git Operations ─────────────────────────────────────────

class TestGitOperations(unittest.TestCase):
    """Tests for git operations (status, push, pull, commit, etc.)"""

    def setUp(self):
        from github_bridge import (get_git_status, get_git_remote_url,
                                    git_push, git_pull, git_add_all,
                                    git_commit, git_create_branch, _get_git_root)
        self.get_status = get_git_status
        self.get_remote_url = get_git_remote_url
        self.push = git_push
        self.pull = git_pull
        self.add_all = git_add_all
        self.commit = git_commit
        self.create_branch = git_create_branch
        self.get_root = _get_git_root

    @patch("subprocess.run")
    def test_git_status_clean(self, mock_run):
        """Simulate clean working tree"""
        def side_effect(cmd, **kwargs):
            mock = MagicMock()
            if "rev-parse --abbrev-ref" in " ".join(cmd):
                mock.returncode = 0
                mock.stdout = "main\n"
            elif "status --porcelain" in " ".join(cmd):
                mock.returncode = 0
                mock.stdout = ""
            elif "rev-list" in " ".join(cmd):
                mock.returncode = 0
                mock.stdout = "0 0\n"
            else:
                mock.returncode = 1
                mock.stdout = ""
            return mock
        mock_run.side_effect = side_effect

        status = self.get_status()
        self.assertEqual(status.get("branch"), "main")
        self.assertTrue(status.get("is_clean"))

    @patch("subprocess.run")
    def test_git_status_dirty(self, mock_run):
        """Simulate dirty working tree"""
        def side_effect(cmd, **kwargs):
            mock = MagicMock()
            if "rev-parse --abbrev-ref" in " ".join(cmd):
                mock.returncode = 0
                mock.stdout = "work/new-feature\n"
            elif "status --porcelain" in " ".join(cmd):
                mock.returncode = 0
                mock.stdout = " M src/file.py\n?? newfile.txt\n"
            elif "rev-list" in " ".join(cmd):
                mock.returncode = 0
                mock.stdout = "1 2\n"
            else:
                mock.returncode = 1
                mock.stdout = ""
            return mock
        mock_run.side_effect = side_effect

        status = self.get_status()
        self.assertEqual(status.get("branch"), "work/new-feature")
        self.assertFalse(status.get("is_clean"))
        self.assertEqual(len(status.get("modified", [])), 1)
        self.assertEqual(len(status.get("untracked", [])), 1)

    @patch("subprocess.run")
    def test_get_remote_url(self, mock_run):
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = "https://github.com/user/repo.git\n"
        mock_run.return_value = mock

        url = self.get_remote_url("origin")
        self.assertEqual(url, "https://github.com/user/repo.git")

    @patch("subprocess.run")
    def test_get_remote_url_not_found(self, mock_run):
        mock = MagicMock()
        mock.returncode = 1
        mock.stdout = ""
        mock_run.return_value = mock

        url = self.get_remote_url("origin")
        self.assertIsNone(url)

    @patch("subprocess.run")
    def test_git_push_success(self, mock_run):
        # Calls: 1) _get_git_root 2) get_git_remote_url→_get_git_root 3) remote get-url 4) actual push
        mock_ret = lambda rc, out: MagicMock(returncode=rc, stdout=out, stderr="")

        mock_run.side_effect = [
            mock_ret(0, "/data/workspace\n"),       # 1: _get_git_root
            mock_ret(0, "/data/workspace\n"),       # 2: get_git_remote_url→_get_git_root
            mock_ret(0, "https://github.com/user/repo.git\n"),  # 3: remote get-url
            mock_ret(0, "To github.com:user/repo.git\n   abc..def  main -> main\n"),  # 4: push
        ]

        result = self.push("origin", "main", token="ghp_test")
        self.assertTrue(result.get("success"))
        # Should have used token-authenticated URL
        push_cmd = mock_run.call_args_list[3][0][0]  # fourth call args
        self.assertIn("x-access-token", " ".join(push_cmd))

    @patch("subprocess.run")
    def test_git_push_failure(self, mock_run):
        # Calls: 1) _get_git_root 2) get_git_remote_url→_get_git_root 3) remote get-url 4) push
        mock_ret = lambda rc, out, err="": MagicMock(returncode=rc, stdout=out, stderr=err)

        mock_run.side_effect = [
            mock_ret(0, "/data/workspace\n"),                             # 1
            mock_ret(0, "/data/workspace\n"),                             # 2
            mock_ret(0, "https://github.com/user/repo.git\n"),           # 3
            mock_ret(128, "", "fatal: Could not read from remote repository."),  # 4
        ]

        result = self.push("origin", "main", token="ghp_test")
        self.assertFalse(result.get("success"))
        self.assertIn("fatal", result.get("error", ""))

    @patch("subprocess.run")
    def test_git_commit_success(self, mock_run):
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = "[main abc1234] My commit message\n 1 file changed, 1 insertion(+)\n"
        mock_run.return_value = mock

        result = self.commit("My commit message")
        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("sha"), "abc1234")

    @patch("subprocess.run")
    def test_git_commit_nothing(self, mock_run):
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = ""
        mock.stderr = "nothing to commit, working tree clean"
        mock_run.return_value = mock

        result = self.commit("Nothing to see")
        self.assertTrue(result.get("success"))

    @patch("subprocess.run")
    def test_git_add_all_success(self, mock_run):
        mock = MagicMock()
        mock.returncode = 0
        mock_run.return_value = mock

        result = self.add_all()
        self.assertTrue(result.get("success"))

    @patch("subprocess.run")
    def test_git_create_branch(self, mock_run):
        mock = MagicMock()
        mock.returncode = 0
        mock_run.return_value = mock

        result = self.create_branch("work/feature")
        self.assertTrue(result.get("success"))

    def test_get_git_root(self):
        """Should return a non-empty path"""
        root = self.get_root()
        self.assertTrue(os.path.isdir(root))


# ── Test Push Current Branch (convenience wrapper) ─────────────

class TestPushCurrentBranch(unittest.TestCase):
    """Tests for push_current_branch convenience wrapper"""

    def setUp(self):
        from github_bridge import push_current_branch
        self.push_current = push_current_branch

    @patch("github_bridge.get_active_token")
    @patch("github_bridge.validate_token")
    @patch("github_bridge.get_git_status")
    @patch("github_bridge.git_push")
    def test_push_current_success(self, mock_push, mock_status,
                                   mock_validate, mock_token):
        mock_token.return_value = "ghp_valid"
        mock_validate.return_value = {"valid": True, "user": "testuser"}
        mock_status.return_value = {"branch": "main"}
        mock_push.return_value = {"success": True, "output": "Everything up-to-date"}

        result = self.push_current("testuser")
        self.assertTrue(result.get("success"))

    @patch("github_bridge.get_active_token")
    def test_push_current_no_token(self, mock_token):
        mock_token.return_value = ""
        result = self.push_current("testuser")
        self.assertFalse(result.get("success"))
        self.assertIn("No GitHub token", result.get("error", ""))


if __name__ == "__main__":
    unittest.main()
