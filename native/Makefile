# Builds the SODA helper. -rdynamic exports tmpfile() so it interposes
# libsoda.so's own call (the sandbox probe).
CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra
soda_helper: soda_helper.c
	$(CC) $(CFLAGS) -rdynamic -o $@ soda_helper.c -ldl -lpthread
clean:
	rm -f soda_helper
