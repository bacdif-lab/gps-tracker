#!/bin/sh
set -e

if [ -z "$(find /etc/nginx/conf.d -maxdepth 1 -name '*.conf')" ]; then
  echo "no configs" >&2
  exit 1
fi

