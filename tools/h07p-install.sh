#!/bin/sh
# First-install bootstrap: Debian's APT installs Python/dependencies before postinst.
set -eu
case "$(uname -s)" in Linux) ;; *) echo 'H07P: bản cài này dành cho Debian Linux amd64.' >&2; exit 1;; esac
assume_yes=no
package=
for arg in "$@"; do
  case "$arg" in --yes) assume_yes=yes;; --help|-h) echo 'Dùng: sh h07p-install.sh [FILE.deb] [--yes]. Nếu đã cài, chạy sudo h07p-setup để mở menu.'; exit 0;; *) [ -z "$package" ] || { echo 'Chỉ chọn một file .deb.' >&2; exit 1; }; package=$arg;; esac
done
if [ -z "$package" ]; then
  if [ -x /usr/sbin/h07p-setup ]; then exec /usr/sbin/h07p-setup; fi
  location=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
  count=0
  for candidate in "$location"/huou07-playground_*_amd64.deb; do
    [ -f "$candidate" ] || continue
    package=$candidate; count=$((count+1))
  done
  [ "$count" -eq 1 ] || { echo 'Đặt script cạnh một file H07P .deb, hoặc truyền đường dẫn file .deb.' >&2; exit 1; }
fi
if [ "$(id -u)" != 0 ]; then
  if [ "$assume_yes" = yes ]; then exec sudo -- sh "$0" "$package" --yes; fi
  exec sudo -- sh "$0" "$package"
fi
[ "$(dpkg --print-architecture)" = amd64 ] || { echo 'Chỉ hỗ trợ Debian amd64; không đổi kiến trúc hệ thống.' >&2; exit 1; }
[ -f "$package" ] || { echo 'Không tìm thấy bộ cài.' >&2; exit 1; }
directory=$(CDPATH= cd -- "$(dirname -- "$package")" && pwd)
package=$directory/$(basename -- "$package")
[ "$(dpkg-deb --field "$package" Package)" = huou07-playground ] || { echo 'File này không phải gói H07P.' >&2; exit 1; }
[ "$(dpkg-deb --field "$package" Architecture)" = amd64 ] || { echo 'Sai kiến trúc bộ cài.' >&2; exit 1; }
digest=$(sha256sum -- "$package" | cut -d ' ' -f 1)
if [ -f "$package.sha256" ]; then
  expected=$(awk 'NF {print $1;exit}' "$package.sha256")
  [ "$expected" = "$digest" ] || { echo 'Checksum không khớp. Dừng cài; tải lại bộ cài.' >&2; exit 1; }
else
  echo 'Không có checksum đi kèm; chỉ tiếp tục nếu đây là bộ cài bạn tin cậy.'
fi
log=$(mktemp /tmp/h07p-install.XXXXXX)
trap 'rm -f -- "$log"' EXIT HUP INT TERM
show_log() {
  sed -E 's#(https?://)[^/[:space:]@]+@#\1[redacted]@#g' "$log" | awk '
    { lower=tolower($0); begin=(lower ~ /-----begin .*private key/); end=(lower ~ /-----end .*private key/);
      hide=private || begin || length($0)>8192 || lower ~ /authorization|api[_-]?key|password|refresh[_-]?token|access[_-]?token|client[_-]?secret|bearer |ghp_|github_pat_|sk-/;
      if(hide) print "[H07P: nội dung nhạy cảm đã được che]"; else print;
      if(begin) private=1; if(end) private=0;
    }'
}
echo 'Đang kiểm tra dependency; chưa thay đổi hệ thống...'
if ! apt-get --simulate --no-remove --no-install-recommends install "$package" >"$log" 2>&1; then
  show_log
  echo 'Không cài được. Kiểm tra kết nối mạng/kho gói hoặc tiến trình quản lý gói đang chạy. H07P không tự gỡ gói khác hay nâng cấp hệ điều hành.' >&2
  exit 1
fi
show_log
if [ "$assume_yes" != yes ]; then
  printf 'Cài H07P theo kế hoạch trên và giữ dữ liệu/native login? [y/N]: '
  read -r answer
  case "$answer" in y|Y|yes|co|có) ;; *) echo 'Đã hủy; chưa thay đổi hệ thống.'; exit 0;; esac
fi
cache=/var/cache/huou07-playground
[ ! -L "$cache" ] || { echo 'Cache là symlink; dừng để bảo vệ hệ thống.' >&2; exit 1; }
if [ ! -e "$cache" ]; then install -d -o root -g root -m 0755 "$cache"; fi
[ -d "$cache" ] || { echo 'Cache không phải thư mục; chưa thay đổi đường dẫn xung đột.' >&2; exit 1; }
[ "$(stat -c %u "$cache")" = 0 ] || { echo 'Cache không do root quản lý.' >&2; exit 1; }
mode=$(stat -c %a "$cache")
[ $((0$mode & 0022)) -eq 0 ] || { echo 'Cache có quyền ghi không an toàn.' >&2; exit 1; }
version=$(dpkg-deb --field "$package" Version)
case "$version" in ''|*[!a-zA-Z0-9.+:~_-]*) echo 'Phiên bản không hợp lệ.' >&2; exit 1;; esac
incoming=$(mktemp "$cache/.incoming.XXXXXX")
cp -- "$package" "$incoming"
[ "$(sha256sum -- "$incoming" | cut -d ' ' -f 1)" = "$digest" ] || { rm -f -- "$incoming"; echo 'Bộ cài thay đổi trong lúc sao chép.' >&2; exit 1; }
chmod 0644 "$incoming"
cached=$cache/huou07-playground_${version}_amd64.deb
mv -f -- "$incoming" "$cached"
printf '%s  %s\n' "$digest" "$(basename -- "$cached")" >"$cached.sha256"
echo 'Đang cài H07P và dependency. Thao tác có thể mất vài phút; không tắt máy...'
if ! apt-get --yes --no-remove --no-install-recommends install "$cached" >"$log" 2>&1; then
  show_log
  echo 'Cài chưa hoàn tất; không xóa dữ liệu hay credentials. Dùng sudo h07p-setup doctor/repair nếu menu đã được cài.' >&2
  exit 1
fi
show_log
echo 'Đã cài H07P. Dùng ứng dụng “H07P — Cài đặt và sửa lỗi” hoặc sudo h07p-setup.'
exec /usr/sbin/h07p-setup doctor
