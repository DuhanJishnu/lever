# Accept padded usernames in `is_admin()`

`is_admin(name)` in `auth.py` rejects `"  admin "` (surrounding whitespace)
even though it is the admin name. Strip surrounding whitespace before
comparing. Do not accept anything that is not exactly the admin name
(e.g. `"administrator"` must stay rejected).
