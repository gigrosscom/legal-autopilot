"""Sign-in and identity: one-time codes by e-mail or SMS, ЭЦП (NCALayer + NCANode) and eGov Mobile QR.

Every method ends the same way (`service.link_or_login`): the verified identifier is attached to the
current anonymous user, or — if another account already owns it — the current user's cases move to that
account and its token is returned. Identifiers are stored only as HMAC hashes plus a masked display form.
"""
