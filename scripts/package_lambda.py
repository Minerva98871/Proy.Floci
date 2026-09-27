import os
import sys
import zipfile


output_directory = sys.argv[1]
archive_path = os.path.join(output_directory, "lomax-thumbnail.zip")
with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
    for root, _, filenames in os.walk("/opt/task"):
        for filename in filenames:
            source = os.path.join(root, filename)
            archive.write(source, os.path.relpath(source, "/opt/task"))
print(archive_path)