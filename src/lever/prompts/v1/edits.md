Replace one exact block per edit. If a block matches several places, add more
surrounding context or set replace_all. When renaming a function, update all
call sites in the same edit or the next one, or Python raises NameError.
Prefer one edit spanning def + call sites; never answer done while a rename
warning is outstanding.
