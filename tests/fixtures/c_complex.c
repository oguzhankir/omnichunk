/* Fixture: C module for extended-language chunking tests. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define BUFFER_CAP 256
#define VERSION_MAJOR 1
#define VERSION_MINOR 2

typedef unsigned long hash_t;

struct point {
    int x;
    int y;
};

typedef struct point point_t;

typedef struct {
    char name[BUFFER_CAP];
    hash_t id;
} record_t;

static hash_t djb2(const char *str) {
    hash_t h = 5381;
    int c;
    while ((c = (unsigned char)*str++)) {
        h = ((h << 5) + h) + (hash_t)c;
    }
    return h;
}

static void record_init(record_t *r, const char *nm, hash_t hid) {
    if (r == NULL || nm == NULL) {
        return;
    }
    strncpy(r->name, nm, BUFFER_CAP - 1);
    r->name[BUFFER_CAP - 1] = '\0';
    r->id = hid;
}

static int point_dist_sq(const point_t *a, const point_t *b) {
    int dx = a->x - b->x;
    int dy = a->y - b->y;
    return dx * dx + dy * dy;
}

int geometry_compare(const point_t *p, const point_t *q) {
    if (p == NULL || q == NULL) {
        return -1;
    }
    return point_dist_sq(p, q);
}

void dump_record(const record_t *r) {
    if (r == NULL) {
        puts("(null record)");
        return;
    }
    printf("record %s id=%lu\n", r->name, (unsigned long)r->id);
}

int main(int argc, char **argv) {
    point_t a = {3, 4};
    point_t b = {0, 0};
    record_t rec;
    (void)argc;
    (void)argv;
    record_init(&rec, "alpha", djb2("alpha"));
    printf("dist_sq=%d v%d.%d\n", geometry_compare(&a, &b), VERSION_MAJOR, VERSION_MINOR);
    dump_record(&rec);
    return EXIT_SUCCESS;
}
