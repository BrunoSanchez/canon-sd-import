# canon-sd-import
Safely copy Canon photos from an SD card to an HDD (one folder per day) and summarize storage by day.

## Usage
```bash
pip install -e .
canon-import /path/to/SD/DCIM /path/to/HDD/CanonR50Pictures --dry-run   # plan only, writes nothing
canon-import /path/to/SD/DCIM /path/to/HDD/CanonR50Pictures             # interactive import
canon-summary /path/to/SD/DCIM /path/to/HDD/CanonR50Pictures
```

## Fast comparison vs `--deep`
By default a file already in the backup counts as "present" when it has the same name, the same
size **and** the same modification time (within 2 seconds, to tolerate FAT/exFAT timestamp
granularity). No file contents are read while planning, so a dry run only lists directories.
Files copied by this tool keep the source mtime, so they match on later runs.

A file with the same name but a different size or mtime is never treated as identical and never
overwritten: it is planned as a copy under a unique name (`IMG_0001_1.CR3`).

`--deep` restores the slow, thorough check: same-size files are compared by full SHA-256 of the
source and the destination (this reads everything, so it can take a long time).

## Progress bar
Scanning, planning, copying and verifying show a progress bar on stderr (files, percent, bytes,
MB/s and ETA). On a terminal it updates in place; otherwise it prints an occasional plain line.
Use `--no-progress` to turn it off. `canon-summary` shows it too (it never hashes).

## Why is it slow?
- SD card read speed (often 20-90 MB/s in practice) and the card reader / USB port (use USB 3 directly, no hub).
- exFAT and external HDDs are slow with many files and with fsync.
- Real copies verify each file by re-reading it from the destination after writing. This is deliberate and is what makes the backup safe, so a copy takes roughly twice the I/O of a plain copy.
- `--deep` reads every already-backed-up file from both the SD card and the HDD.
