#include <cjson/cJSON.h>
#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_HOPS 32
#define MAX_FLOWS 64
#define MAX_EPOCHS 16
#define MAX_INCIDENTS 64
#define MAX_ADM 128
#define MAX_DEN 128
#define MAX_LED 128

typedef struct {
  char flow_id[64];
  int epoch;
  char hop_id[32];
  int bytes;
} Flow;

typedef struct {
  char kind[32];
  int epoch;
  char hop_id[32];
  int delta;
} Incident;

static char *read_file(const char *path) {
  FILE *f = fopen(path, "rb");
  if (!f) return NULL;
  if (fseek(f, 0, SEEK_END) != 0) {
    fclose(f);
    return NULL;
  }
  long sz = ftell(f);
  if (sz < 0) {
    fclose(f);
    return NULL;
  }
  rewind(f);
  char *buf = malloc((size_t)sz + 1);
  if (!buf) {
    fclose(f);
    return NULL;
  }
  if (fread(buf, 1, (size_t)sz, f) != (size_t)sz) {
    free(buf);
    fclose(f);
    return NULL;
  }
  buf[sz] = '\0';
  fclose(f);
  return buf;
}

static cJSON *load_json(const char *path) {
  char *raw = read_file(path);
  if (!raw) return NULL;
  cJSON *j = cJSON_Parse(raw);
  free(raw);
  return j;
}

static int env_or(const char *key, const char *defv, char *out, size_t outsz) {
  const char *v = getenv(key);
  const char *use = v && v[0] ? v : defv;
  snprintf(out, outsz, "%s", use);
  return 0;
}

static int cmp_path_row(const void *a, const void *b) {
  return strcmp((const char *)a, (const char *)b);
}

static int list_json_paths(const char *dir, char paths[][512], int maxn) {
  DIR *d = opendir(dir);
  if (!d) return 0;
  int n = 0;
  struct dirent *ent;
  while ((ent = readdir(d)) != NULL && n < maxn) {
    size_t len = strlen(ent->d_name);
    if (len < 6 || strcmp(ent->d_name + len - 5, ".json") != 0) continue;
    snprintf(paths[n], 512, "%s/%s", dir, ent->d_name);
    n++;
  }
  closedir(d);
  qsort(paths, (size_t)n, sizeof(paths[0]), cmp_path_row);
  return n;
}

static int cap_core(const char *hop, int *base, int *delta, int *halted,
                    const char hops_order[][32], int nh) {
  int hidx = -1;
  for (int i = 0; i < nh; i++) {
    if (strcmp(hops_order[i], hop) == 0) {
      hidx = i;
      break;
    }
  }
  if (hidx < 0) return 0;
  if (halted[hidx]) return 0;
  int v = base[hidx] + delta[hidx];
  return v < 1 ? 1 : v;
}

static int imin(int a, int b) { return a < b ? a : b; }
static int imax(int a, int b) { return a > b ? a : b; }

int main(void) {
  char data_dir[512], audit_dir[512];
  env_or("CRA_DATA_DIR", "/app/relayhop", data_dir, sizeof data_dir);
  env_or("CRA_AUDIT_DIR", "/app/audit", audit_dir, sizeof audit_dir);

  char pol_path[768];
  snprintf(pol_path, sizeof pol_path, "%s/policy.json", data_dir);
  cJSON *pol = load_json(pol_path);
  if (!pol) return 1;

  int carry_max = cJSON_GetObjectItem(pol, "carry_max")->valueint;
  cJSON *epochs_j = cJSON_GetObjectItem(pol, "epochs");
  cJSON *hops_j = cJSON_GetObjectItem(pol, "hops_order");
  int nepochs = cJSON_GetArraySize(epochs_j);
  int nh = cJSON_GetArraySize(hops_j);
  if (nh > MAX_HOPS || nepochs > MAX_EPOCHS) return 1;

  int epochs[MAX_EPOCHS];
  char hops_order[MAX_HOPS][32];
  for (int i = 0; i < nepochs; i++)
    epochs[i] = cJSON_GetArrayItem(epochs_j, i)->valueint;
  for (int i = 0; i < nh; i++)
    snprintf(hops_order[i], 32, "%s",
             cJSON_GetArrayItem(hops_j, i)->valuestring);

  char inc_path[768];
  snprintf(inc_path, sizeof inc_path, "%s/incidents.json", data_dir);
  cJSON *inc_file = load_json(inc_path);
  if (!inc_file) return 1;
  cJSON *incidents = cJSON_GetObjectItem(inc_file, "incidents");
  int ninc = cJSON_GetArraySize(incidents);

  int base[MAX_HOPS] = {0};
  char hop_paths[32][512];
  char hops_dir[768];
  snprintf(hops_dir, sizeof hops_dir, "%s/hops", data_dir);
  int nhfiles = list_json_paths(hops_dir, hop_paths, 32);
  for (int i = 0; i < nhfiles; i++) {
    cJSON *hf = load_json(hop_paths[i]);
    if (!hf) return 1;
    const char *hid = cJSON_GetObjectItem(hf, "hop_id")->valuestring;
    int bc = cJSON_GetObjectItem(hf, "base_cap")->valueint;
    for (int j = 0; j < nh; j++) {
      if (strcmp(hops_order[j], hid) == 0) {
        base[j] = bc;
        break;
      }
    }
    cJSON_Delete(hf);
  }

  Flow flows[MAX_FLOWS];
  int nflows = 0;
  char flow_paths[64][512];
  char flows_dir[768];
  snprintf(flows_dir, sizeof flows_dir, "%s/flows", data_dir);
  int nffiles = list_json_paths(flows_dir, flow_paths, 64);
  for (int i = 0; i < nffiles && nflows < MAX_FLOWS; i++) {
    cJSON *ff = load_json(flow_paths[i]);
    if (!ff) return 1;
    snprintf(flows[nflows].flow_id, 64, "%s",
             cJSON_GetObjectItem(ff, "flow_id")->valuestring);
    flows[nflows].epoch = cJSON_GetObjectItem(ff, "epoch")->valueint;
    snprintf(flows[nflows].hop_id, 32, "%s",
             cJSON_GetObjectItem(ff, "hop_id")->valuestring);
    flows[nflows].bytes = cJSON_GetObjectItem(ff, "bytes")->valueint;
    nflows++;
    cJSON_Delete(ff);
  }

  int delta[MAX_HOPS] = {0};
  int halted[MAX_HOPS] = {0};
  int carry[MAX_HOPS] = {0};
  for (int i = 0; i < nh; i++) {
    delta[i] = 0;
    halted[i] = 0;
    carry[i] = 0;
  }

  cJSON *admissions = cJSON_CreateArray();
  cJSON *denials = cJSON_CreateArray();
  cJSON *ledgers = cJSON_CreateArray();

  for (int ei = 0; ei < nepochs; ei++) {
    int e = epochs[ei];
    for (int ii = 0; ii < ninc; ii++) {
      cJSON *inc = cJSON_GetArrayItem(incidents, ii);
      if (cJSON_GetObjectItem(inc, "epoch")->valueint != e) continue;
      const char *kind = cJSON_GetObjectItem(inc, "kind")->valuestring;
      if (strcmp(kind, "noop") == 0) continue;
      cJSON *hop_item = cJSON_GetObjectItem(inc, "hop_id");
      if (!hop_item || !cJSON_IsString(hop_item)) return 1;
      const char *hid = hop_item->valuestring;
      int hidx = -1;
      for (int j = 0; j < nh; j++) {
        if (strcmp(hops_order[j], hid) == 0) {
          hidx = j;
          break;
        }
      }
      if (strcmp(kind, "cap_add") == 0) {
        if (hidx >= 0)
          delta[hidx] += cJSON_GetObjectItem(inc, "delta")->valueint;
      } else if (strcmp(kind, "halt_hop") == 0) {
        if (hidx >= 0) {
          halted[hidx] = 1;
          carry[hidx] = 0;
        }
      } else if (strcmp(kind, "resume_hop") == 0) {
        if (hidx >= 0) {
          halted[hidx] = 0;
          carry[hidx] = 0;
        }
      } else {
        return 1;
      }
    }

    int cin[MAX_HOPS];
    int used[MAX_HOPS];
    for (int i = 0; i < nh; i++) {
      cin[i] = carry[i];
      used[i] = 0;
    }

    int epoch_flow_idx[MAX_FLOWS];
    int nepoch_flows = 0;
    for (int fi = 0; fi < nflows; fi++) {
      if (flows[fi].epoch == e) epoch_flow_idx[nepoch_flows++] = fi;
    }
    for (int a = 0; a < nepoch_flows; a++) {
      for (int b = a + 1; b < nepoch_flows; b++) {
        Flow *fa = &flows[epoch_flow_idx[a]];
        Flow *fb = &flows[epoch_flow_idx[b]];
        int swap = 0;
        if (strcmp(fa->hop_id, fb->hop_id) < 0)
          swap = 0;
        else if (strcmp(fa->hop_id, fb->hop_id) > 0)
          swap = 1;
        else if (strcmp(fa->flow_id, fb->flow_id) > 0)
          swap = 1;
        if (swap) {
          int t = epoch_flow_idx[a];
          epoch_flow_idx[a] = epoch_flow_idx[b];
          epoch_flow_idx[b] = t;
        }
      }
    }

    for (int fi = 0; fi < nepoch_flows; fi++) {
      Flow *f = &flows[epoch_flow_idx[fi]];
      int hidx = -1;
      for (int j = 0; j < nh; j++) {
        if (strcmp(hops_order[j], f->hop_id) == 0) {
          hidx = j;
          break;
        }
      }
      if (hidx < 0) continue;
      int cc = cap_core(f->hop_id, base, delta, halted, hops_order, nh);
      int bud = cc + cin[hidx];
      int avail = bud - used[hidx];
      if (avail < 0) avail = 0;
      if (f->bytes <= avail) {
        used[hidx] += f->bytes;
        cJSON *row = cJSON_CreateObject();
        cJSON_AddNumberToObject(row, "bytes", f->bytes);
        cJSON_AddNumberToObject(row, "epoch", e);
        cJSON_AddStringToObject(row, "flow_id", f->flow_id);
        cJSON_AddStringToObject(row, "hop_id", f->hop_id);
        cJSON_AddItemToArray(admissions, row);
      } else {
        cJSON *row = cJSON_CreateObject();
        cJSON_AddNumberToObject(row, "available", avail);
        cJSON_AddNumberToObject(row, "epoch", e);
        cJSON_AddStringToObject(row, "flow_id", f->flow_id);
        cJSON_AddStringToObject(row, "hop_id", f->hop_id);
        cJSON_AddNumberToObject(row, "requested", f->bytes);
        cJSON_AddItemToArray(denials, row);
      }
    }

    for (int hi = 0; hi < nh; hi++) {
      int cc = cap_core(hops_order[hi], base, delta, halted, hops_order, nh);
      int bud = cc + cin[hi];
      int u = used[hi];
      int rem = bud - u;
      int cout = imin(carry_max, imax(0, rem));
      if (halted[hi]) cout = 0;
      cJSON *row = cJSON_CreateObject();
      cJSON_AddNumberToObject(row, "cap_core", cc);
      cJSON_AddNumberToObject(row, "carry_in", cin[hi]);
      cJSON_AddNumberToObject(row, "carry_out", cout);
      cJSON_AddNumberToObject(row, "epoch", e);
      cJSON_AddStringToObject(row, "hop_id", hops_order[hi]);
      cJSON_AddNumberToObject(row, "used", u);
      cJSON_AddItemToArray(ledgers, row);
      carry[hi] = cout;
    }
  }

  cJSON *applied = cJSON_CreateArray();
  for (int ii = 0; ii < ninc; ii++) {
    cJSON *inc = cJSON_GetArrayItem(incidents, ii);
    cJSON_AddItemToArray(
        applied,
        cJSON_CreateString(cJSON_GetObjectItem(inc, "kind")->valuestring));
  }

  int max_ep = 0;
  for (int ii = 0; ii < ninc; ii++) {
    cJSON *inc = cJSON_GetArrayItem(incidents, ii);
    int ep = cJSON_GetObjectItem(inc, "epoch")->valueint;
    if (ep > max_ep) max_ep = ep;
  }
  cJSON *child;
  cJSON_ArrayForEach(child, admissions) {
    int ep = cJSON_GetObjectItem(child, "epoch")->valueint;
    if (ep > max_ep) max_ep = ep;
  }
  cJSON_ArrayForEach(child, denials) {
    int ep = cJSON_GetObjectItem(child, "epoch")->valueint;
    if (ep > max_ep) max_ep = ep;
  }

  int tot_adm = 0, tot_adm_bytes = 0;
  cJSON_ArrayForEach(child, admissions) {
    tot_adm++;
    tot_adm_bytes += cJSON_GetObjectItem(child, "bytes")->valueint;
  }
  int tot_den = cJSON_GetArraySize(denials);
  int tot_den_bytes = 0;
  cJSON_ArrayForEach(child, denials) {
    tot_den_bytes += cJSON_GetObjectItem(child, "requested")->valueint;
  }

  cJSON *summary = cJSON_CreateObject();
  cJSON_AddItemToObject(summary, "incidents_applied", applied);
  cJSON_AddNumberToObject(summary, "max_epoch", max_ep);
  cJSON_AddNumberToObject(summary, "total_admissions", tot_adm);
  cJSON_AddNumberToObject(summary, "total_admitted_bytes", tot_adm_bytes);
  cJSON_AddNumberToObject(summary, "total_denials", tot_den);
  cJSON_AddNumberToObject(summary, "total_denied_bytes", tot_den_bytes);

  char out_path[768];
  snprintf(out_path, sizeof out_path, "%s/admissions.json", audit_dir);
  cJSON *root = cJSON_CreateObject();
  cJSON_AddItemToObject(root, "admissions", cJSON_Duplicate(admissions, 1));
  char *printed = cJSON_Print(root);
  FILE *wf = fopen(out_path, "w");
  if (printed && wf) {
    fputs(printed, wf);
    fputc('\n', wf);
    fclose(wf);
  }
  free(printed);
  cJSON_Delete(root);

  snprintf(out_path, sizeof out_path, "%s/denials.json", audit_dir);
  root = cJSON_CreateObject();
  cJSON_AddItemToObject(root, "denials", cJSON_Duplicate(denials, 1));
  printed = cJSON_Print(root);
  wf = fopen(out_path, "w");
  if (printed && wf) {
    fputs(printed, wf);
    fputc('\n', wf);
    fclose(wf);
  }
  free(printed);
  cJSON_Delete(root);

  snprintf(out_path, sizeof out_path, "%s/carry_ledgers.json", audit_dir);
  root = cJSON_CreateObject();
  cJSON_AddItemToObject(root, "rows", cJSON_Duplicate(ledgers, 1));
  printed = cJSON_Print(root);
  wf = fopen(out_path, "w");
  if (printed && wf) {
    fputs(printed, wf);
    fputc('\n', wf);
    fclose(wf);
  }
  free(printed);
  cJSON_Delete(root);

  snprintf(out_path, sizeof out_path, "%s/summary.json", audit_dir);
  printed = cJSON_Print(summary);
  wf = fopen(out_path, "w");
  if (printed && wf) {
    fputs(printed, wf);
    fputc('\n', wf);
    fclose(wf);
  }
  free(printed);

  cJSON_Delete(pol);
  cJSON_Delete(inc_file);
  cJSON_Delete(admissions);
  cJSON_Delete(denials);
  cJSON_Delete(ledgers);
  cJSON_Delete(summary);
  return 0;
}
