import hashlib
import json
import os
import pickle
import shutil
from pathlib import Path

import numpy as np
import requests


class ServerError(BaseException):
    pass


# class Config:
#     host = "http://127.0.0.1:1234"
#     cwd = Path("./")
#     test_folder = Path("data/assignments")
#     test_path = test_folder / "local_tests.pickle"


class Config:
    host = "http://161.35.93.12:1234"
    cwd = Path("./")
    test_folder = Path("local_tests")
    test_path = test_folder / "local_tests.pickle"


def get_progress(username):
    endpoint = f"{Config.host}/get_progress/{username}"
    response = requests.get(endpoint)
    data = response.json()

    if "error" in data:
        raise ServerError(data["error"])

    completed = 0
    for k, v in data["progress"].items():
        if v == "completed":
            completed += 1
    completed_percentage = round(completed / len(data["progress"]) * 100)

    print(
        "| Current Assignment Grade {:2}%              |".format(completed_percentage)
    )
    for k, v in sorted(data["progress"].items()):
        print("| {:25}| {:15}|".format(k, v))


# Local tests
def _remove_local_tests():
    try:
        Config.test_path.unlink()
        print(
            "Current version of local tests is deprecated. Outdated tests are removed."
        )
    except FileNotFoundError:
        pass


def _download_local_tests(username):
    """Download local_tests.pickle to client.

    - Requests from endpoint: /load_tests/{username}
      - endpoint uses LOCAL_TESTS on server

    """
    if not os.path.exists(Config.test_folder):
        os.makedirs(Config.test_folder)

    try:
        endpoint = f"{Config.host}/load_tests/{username}"
        stream = requests.get(endpoint, stream=True)
        if stream.status_code == 200:
            with open(Config.test_path, "wb") as f:
                stream.raw.decode_content = True
                shutil.copyfileobj(stream.raw, f)
            print("Local tests are downloaded.")
        else:
            error = stream.json()["error"]
            raise ServerError(error)
    except ServerError as e:
        raise e
    except:
        raise ServerError("Error downloading local tests.")


def _local_tests_are_valid():
    """Confirm that local_tests.pickle is the same on server and client.

    - Computes md5 hash for local_tests.pickle on client
    - Sends to endpoint: /check_sum/{local_md5}
      - endpoint checks LOCAL_TESTS on server

    """
    try:
        hash_md5 = hashlib.md5()
        with open(Config.test_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        local_md5 = hash_md5.hexdigest()
        endpoint = f"{Config.host}/check_sum/{local_md5}"
        response = requests.get(endpoint).json()
        return response["success"]
    except:
        return False


def _passed_local_tests(function, arg_keys):
    """Execute functions and check results of local tests.

    - No communication with endpoints.
    - Assumes data has keys: "inputs", "outputs"
      - each is an array of 100 examples
      - inputs further are dicts with arg_keys as keys
      - check shape, within tolerance

    """
    with open(Config.test_path, "rb") as f:
        try:
            test_data = pickle.load(f, encoding="latin1")
        except TypeError:
            test_data = pickle.load(f)

    data = test_data[function.__name__]
    inputs = data["inputs"]
    outputs = data["outputs"]

    for in_, out_ in zip(inputs, outputs):
        args_ = {k: in_[k] for k in arg_keys}
        answer = function(**args_)
        if answer.shape != out_.shape or not np.allclose(
            answer, out_, rtol=1e-5, atol=1e-5
        ):
            return False
    return True


# Remote tests
def _passed_remote_test(username, function, arg_keys):
    """Check results with remote tests.

    - Contacts: /get_test_input/{username}/{function.__name__}
        gets  : {
            "username": username,
            "ipd": int(Global.data_dict[assignment]["ipd"][random_ipd]),  # REMOTE_TESTS
            "input": Global.data_dict[assignment]["inputs"][random_ipd],  # REMOTE_TESTS
        }

        assumes:
            - input is a dict with keys as args,
            - values as dicts with keys: "data", "type"
            - if type is ndarray, ensure with `np.array(...)`

            data["input"]
                - X_in : {"data": ..., "type": ...}
                - Y_in : {"data": ..., "type": ...}

    - Runs tests with received inputs
    - Contacts: /check_answer/{username}/{function.__name__}/{data["ipd"]}/{json.dumps(test_result)}
      - sends test result with `np.array(test_result).tolist()`
        - which gets passed to json.dumps(...)

    """
    endpoint = f"{Config.host}/get_test_input/{username}/{function.__name__}"
    response = requests.get(endpoint)
    data = response.json()

    if "error" in data:
        raise ServerError(data["error"])

    args = []
    for key in arg_keys:
        arg_ = data["input"][key]
        arg_value = data["input"][key]["data"]
        if arg_["type"] == "ndarray":
            arg_value = np.array(arg_value)
        args.append(arg_value)

    test_result = function(*args)
    test_result = np.array(test_result).tolist()
    endpoint = f'{Config.host}/check_answer/{username}/{function.__name__}/{data["ipd"]}/{json.dumps(test_result)}'

    response = requests.get(endpoint)
    if not response.status_code == 200:
        raise ServerError("Internal Error Occurred")
    answer_response = response.json()

    return answer_response["success"]


def test_student_function_with_download(username, function, arg_keys):
    if not _local_tests_are_valid():
        _remove_local_tests()
        print("Downloading local tests...")
        _download_local_tests(username)

    print("Running local tests...")
    if _passed_local_tests(function, arg_keys):
        print("{} successfully passed local tests".format(function.__name__))
        print("Running remote test...")

        if _passed_remote_test(username, function, arg_keys):
            print("Test was successful. Congratulations!")
        else:
            print("Test failed. Please review your code.")
    else:
        print("{} failed some local tests".format(function.__name__))


def test_student_function(username, function, arg_keys):
    print("Running local tests...")
    if _passed_local_tests(function, arg_keys):
        print("{} successfully passed local tests".format(function.__name__))
        print("Running remote test...")

        if _passed_remote_test(username, function, arg_keys):
            print("Test was successful. Congratulations!")
        else:
            print("Test failed. Please review your code.")
    else:
        print("{} failed some local tests".format(function.__name__))


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("USAGE: python automark.py USERNAME")
    username = sys.argv[1]
    get_progress(username)
