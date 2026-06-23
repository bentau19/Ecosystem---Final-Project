package com.example.android.domain.entities;

import java.io.InputStream;

// Sized read range: exact byte count + pre-seeked InputStream.
public final class VDriveReadRange {

    public final long available;  // exact bytes the stream will yield
    public final InputStream stream;

    public VDriveReadRange(long available, InputStream stream) {
        this.available = available;
        this.stream    = stream;
    }
}
