from django.contrib.auth.hashers import make_password, check_password
import re

def hash_pw(raw):
    return make_password(raw)

def verify_pw(stored, raw):
    return check_password(raw, stored)

def validate_password_complexity(pwd):
    if not pwd or len(pwd) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r'[a-z]', pwd):
        return False, "Password must contain a lowercase letter."
    if not re.search(r'[A-Z]', pwd):
        return False, "Password must contain an uppercase letter."
    if not re.search(r'\d', pwd):
        return False, "Password must contain a digit."
    if not re.search(r'[^A-Za-z0-9]', pwd):
        return False, "Password must contain a special character."
    return True, ""