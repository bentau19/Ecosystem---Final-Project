package com.example.android.domain.entities;

/**
 * Data model for representing device storage statistics.
 */
public class DeviceStorageStats {
    private final long used;
    private final long total;

    public DeviceStorageStats(long used, long total) {
        this.used = used;
        this.total = total;
    }

    // --- Getters ---

    /**
     * @return The amount of used storage in GB.
     */
    public long getUsed() {
        return used;
    }

    /**
     * @return The total storage capacity in GB.
     */
    public long getTotal() {
        return total;
    }

    // --- Helper Methods ---

    /**
     * Formats the storage info into a human-readable string.
     * @return A string in the format "used/total GB" (e.g., "160/256 GB").
     */
    public String getFormattedStatus() {
        return used + "/" + total + " GB";
    }

    /**
     * Calculates the current storage usage as a percentage.
     * @return Integer representing the percentage of used space.
     */
    public int getUsagePercentage() {
        if (total == 0) return 0;
        return (int) ((used * 100) / total);
    }
}