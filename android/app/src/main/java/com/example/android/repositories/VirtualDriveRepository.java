package com.example.android.repositories;

import com.example.android.data.datasource.VirtualDriveDataSource;
import com.example.android.domain.entities.VDriveEntry;
import com.example.android.domain.entities.VDrivePageResult;
import com.example.android.domain.entities.VDriveReadRange;

import java.io.File;
import java.io.IOException;
import java.io.OutputStream;
import java.util.List;

// Singleton owning VirtualDriveDataSource; delegates all VDrive ops. Pure request→response — no state.
public class VirtualDriveRepository {

    private static VirtualDriveRepository instance;
    private final VirtualDriveDataSource dataSource;

    private VirtualDriveRepository() {
        dataSource = new VirtualDriveDataSource();
    }

    public static synchronized VirtualDriveRepository getInstance() {
        if (instance == null) {
            instance = new VirtualDriveRepository();
        }
        return instance;
    }

    // ── Directory listing ─────────────────────────────────────────────────────

    public List<VDriveEntry> listDir(String virtualPath) throws IOException {
        return dataSource.listDir(virtualPath);
    }

    public VDrivePageResult listDirPage(String virtualPath, String afterName, int limit)
            throws IOException {
        return dataSource.listDirPage(virtualPath, afterName, limit);
    }

    // ── Stat ──────────────────────────────────────────────────────────────────

    public VDriveEntry stat(String virtualPath) throws IOException {
        return dataSource.stat(virtualPath);
    }

    // ── Read ──────────────────────────────────────────────────────────────────

    public VDriveReadRange openReadRangeChecked(String virtualPath, long offset, int length)
            throws IOException {
        return dataSource.openReadRangeChecked(virtualPath, offset, length);
    }

    public boolean exists(String virtualPath) {
        return dataSource.exists(virtualPath);
    }

    // ── Write ─────────────────────────────────────────────────────────────────

    public OutputStream openWriteTemp(String virtualPath) throws IOException {
        return dataSource.openWriteTemp(virtualPath);
    }

    public void finalizeWrite(String virtualPath) throws IOException {
        dataSource.finalizeWrite(virtualPath);
    }

    // ── Mutations ─────────────────────────────────────────────────────────────

    public void create(String virtualPath, boolean isDir) throws IOException {
        dataSource.create(virtualPath, isDir);
    }

    public void delete(String virtualPath) throws IOException {
        dataSource.delete(virtualPath);
    }

    public void rename(String fromVirtual, String toVirtual) throws IOException {
        dataSource.rename(fromVirtual, toVirtual);
    }

    public void truncate(String virtualPath, long newSize) throws IOException {
        dataSource.truncate(virtualPath, newSize);
    }

    // ── Path utilities ────────────────────────────────────────────────────────

    public File resolve(String virtualPath) throws IOException {
        return dataSource.resolve(virtualPath);
    }
}
