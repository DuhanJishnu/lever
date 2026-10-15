Replace one exact block per edit; whitespace differences and small typos are
tolerated when the match is unique. If a block matches several places, add
more surrounding context or set replace_all. When renaming a function, update
all call sites too, or Python raises NameError. Prefer one edit spanning def +
call sites; never answer done while a rename warning is outstanding. A reverted edit means the
replacement would break syntax — fix the replacement, not the file.
