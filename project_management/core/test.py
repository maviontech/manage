import hashlib, base64

def verify_pbkdf2_sha256(stored_hash, candidate):
    # stored_hash like: 'pbkdf2_sha256$1000000$salt$base64dk'
    algo, iter_s, salt, b64_dk = stored_hash.split('$')
    iterations = int(iter_s)
    dk = base64.b64decode(b64_dk)

    # derive key from candidate using same params
    derived = hashlib.pbkdf2_hmac('sha256', candidate.encode('utf-8'), salt.encode('utf-8'), iterations, dklen=len(dk))
    return derived == dk

# Example usage:
stored = "pbkdf2_sha256$1000000$DX3I0ec38XsR4oEPaaDff1$SKHd7MKhM8HY2kI70xLgB27Fokdxn2mfVm9b769h/Tc="
print(verify_pbkdf2_sha256(stored, "candidate_password"))
