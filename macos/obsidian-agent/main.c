#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static const char *allowed_scripts[] = {
    "/Applications/BoomyBoom/run_daily_brief.sh",
    "/Applications/BoomyBoom/run_kr_brief.sh",
    "/Applications/BoomyBoom-Biz/run_daily_brief.sh",
    "/Applications/BoomyBoom-Biz/run_scout.sh",
    "/Applications/BoomyBoom-Biz/run_weekly_synthesis.sh",
    NULL
};

static int is_allowed(const char *path) {
    for (int i = 0; allowed_scripts[i] != NULL; i++) {
        if (strcmp(path, allowed_scripts[i]) == 0) return 1;
    }
    return 0;
}

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--smoke") == 0) {
        char *smoke[] = {
            "/usr/bin/python3",
            "/Applications/BoomyBoom/wiki_tools.py",
            "log",
            "전용 에이전트 launchd 권한 확인",
            NULL
        };
        execv(smoke[0], smoke);
        perror("execv python3");
        return 70;
    }

    if (argc != 2 || !is_allowed(argv[1])) {
        fprintf(stderr, "Denied: only approved BoomyBoom jobs may run.\n");
        return 64;
    }

    char *child[] = {
        "/bin/bash",
        argv[1],
        NULL
    };
    execv(child[0], child);
    perror("execv bash");
    return 70;
}
