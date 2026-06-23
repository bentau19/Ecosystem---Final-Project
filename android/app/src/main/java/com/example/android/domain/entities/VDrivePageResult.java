package com.example.android.domain.entities;

import java.util.List;

// Paginated directory listing result.
public final class VDrivePageResult {

    public final List<VDriveEntry> entries;
    public final boolean hasMore;
    public final String nextAfter; // null when hasMore is false

    public VDrivePageResult(List<VDriveEntry> entries, boolean hasMore, String nextAfter) {
        this.entries   = entries;
        this.hasMore   = hasMore;
        this.nextAfter = nextAfter;
    }
}
