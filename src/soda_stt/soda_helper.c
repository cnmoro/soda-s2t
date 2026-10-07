/*
 * soda_helper - streams audio through Chrome's on-device SODA engine.
 *
 * Usage (argv[0] MUST carry the two Chrome flags; the Python side sets it):
 *     <argv0-with-flags> <libsoda.so> <config.bin>
 *
 * Protocol:
 *   stdin : raw audio, s16le mono at the config's sample rate, streamed.
 *           EOF on stdin -> ExtendedSodaMarkDone().
 *   stdout: one record per SODA event: [uint32 LE length][serialized SodaResponse].
 *
 * The SODA library gates recognition behind a "called by Chrome" check. Two of
 * its conditions are satisfied here: tmpfile() is interposed to fail (a sandbox
 * probe), and argv[0] carries --utility-sub-type / --service-sandbox-type. The
 * remaining conditions (module path, API key) are satisfied by the caller.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

/* Main-executable definition interposes libsoda's tmpfile@plt (build -rdynamic).
   Returning NULL mimics Chrome's sandboxed speech process. */
FILE *tmpfile(void) { return NULL; }

typedef void (*EvCb)(const char *, int, void *);
typedef struct {
  const char *cfg;
  int size;
  EvCb cb;
  void *handle;
} SerializedSodaConfig;

static pthread_mutex_t out_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t stop_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t stop_cond = PTHREAD_COND_INITIALIZER;
static int stopped = 0;

static void on_event(const char *data, int len, void *unused) {
  (void)unused;
  uint32_t n = (uint32_t)len;
  pthread_mutex_lock(&out_lock);
  fwrite(&n, sizeof(n), 1, stdout);
  fwrite(data, 1, (size_t)len, stdout);
  fflush(stdout);
  pthread_mutex_unlock(&out_lock);

  /* SodaResponse.soda_type is field 1 (varint). soda_type == 2 is STOP,
     3 is SHUTDOWN -> either marks the end of the stream. */
  if (len >= 2 && (unsigned char)data[0] == 0x08 &&
      (data[1] == 0x02 || data[1] == 0x03)) {
    pthread_mutex_lock(&stop_lock);
    stopped = 1;
    pthread_cond_signal(&stop_cond);
    pthread_mutex_unlock(&stop_lock);
  }
}

static char *read_file(const char *path, long *out_len) {
  FILE *f = fopen(path, "rb");
  if (!f) return NULL;
  fseek(f, 0, SEEK_END);
  long n = ftell(f);
  rewind(f);
  char *buf = malloc((size_t)n);
  if (buf && fread(buf, 1, (size_t)n, f) != (size_t)n) {
    free(buf);
    buf = NULL;
  }
  fclose(f);
  if (buf) *out_len = n;
  return buf;
}

int main(int argc, char **argv) {
  if (argc < 3) {
    fprintf(stderr, "usage: <argv0-with-flags> <libsoda.so> <config.bin>\n");
    return 2;
  }

  void *lib = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
  if (!lib) {
    fprintf(stderr, "dlopen: %s\n", dlerror());
    return 3;
  }

  void *(*create)(SerializedSodaConfig) = dlsym(lib, "CreateExtendedSodaAsync");
  void (*add_audio)(void *, const char *, int) = dlsym(lib, "ExtendedAddAudio");
  void (*soda_start)(void *) = dlsym(lib, "ExtendedSodaStart");
  void (*mark_done)(void *) = dlsym(lib, "ExtendedSodaMarkDone");
  void (*soda_delete)(void *) = dlsym(lib, "DeleteExtendedSodaAsync");
  if (!create || !add_audio || !soda_start || !mark_done || !soda_delete) {
    fprintf(stderr, "missing SODA entry points\n");
    return 4;
  }

  long cfg_len = 0;
  char *cfg = read_file(argv[2], &cfg_len);
  if (!cfg) {
    fprintf(stderr, "cannot read config %s\n", argv[2]);
    return 5;
  }

  SerializedSodaConfig config = {cfg, (int)cfg_len, on_event, NULL};
  void *handle = create(config);
  if (!handle) {
    fprintf(stderr, "CreateExtendedSodaAsync returned NULL\n");
    return 6;
  }
  soda_start(handle);

  /* Pump stdin -> SODA. ~100ms per chunk at 16kHz mono s16le = 3200 bytes. */
  char chunk[4096];
  size_t got;
  while ((got = fread(chunk, 1, sizeof(chunk), stdin)) > 0)
    add_audio(handle, chunk, (int)got);

  mark_done(handle);

  /* Wait for SODA to emit STOP/SHUTDOWN (final events flushed), with a timeout
     guard so a stuck engine cannot hang the helper forever. */
  {
    struct timespec deadline;
    clock_gettime(CLOCK_REALTIME, &deadline);
    deadline.tv_sec += 30;
    pthread_mutex_lock(&stop_lock);
    while (!stopped) {
      if (pthread_cond_timedwait(&stop_cond, &stop_lock, &deadline) != 0) break;
    }
    pthread_mutex_unlock(&stop_lock);
  }

  soda_delete(handle);
  free(cfg);
  return 0;
}
