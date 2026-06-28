package com.example.android.domain.entities;

import com.example.android.domain.usecases.BackupTransferUseCase;
import com.example.android.enums.BackupFileResult;
import com.example.android.ui.fragments.BackupFragment;

/**
 * User-configured options for a backup operation.
 *
 * <p>Captured in the UI layer ({@link BackupFragment})
 * when the user taps Start, then carried through the full stack — ViewModel → Repository →
 * {@code ConnectivityService} → {@link BackupTransferUseCase}
 * — so that the options are included in the manifest header sent to the PC.
 *
 * <p>This is a pure Java class with zero Android Framework dependencies, keeping the
 * domain layer unit-testable without an emulator.
 *
 * @param classifyImages      Whether the PC should run image classification on the received files.
 *
 *                            <p>Derived from the "Classify junk files" checkbox in
 *                            {@code BackupFragment}: if the checkbox is <b>checked</b> (default),
 *                            {@code classifyImages} is {@code true}; if <b>unchecked</b>, it is {@code false}.
 * @param parallelSlots       Number of file slots to open concurrently on the TauSync transport.
 *
 *                            <p>Android sends {@code parallelSlots} backup slot channels simultaneously
 *                            so that storage I/O for one file overlaps with the network transfer of another.
 *                            The desktop {@code BackupService} already handles parallel slots — it spawns
 *                            one receiver thread per discovered {@code backup_slot_meta_*} channel, regardless
 *                            of how many are open at once.
 *
 *                            <p>Value is clamped to at least 1.  The UI layer computes the default via
 *                            {@code BackupFragment.computeParallelSlots()} using CPU core count and battery
 *                            level; the domain layer treats it as an opaque integer.
 * @param deleteFilesOnBackup Whether the source file should be deleted from the device once the PC has
 *                            confirmed it received and saved the file successfully.
 *
 *                            <p>Derived from the "Delete originals after backup" checkbox in
 *                            {@code BackupFragment}. {@link BackupTransferUseCase}
 *                            only deletes a file when the PC explicitly reports
 *                            {@link BackupFileResult#SUCCESS} ("succ") on the
 *                            corresponding {@code backup_file_result_*} channel — a "fail" result, timeout,
 *                            or read error never triggers deletion.
 * @param storageSaver        Whether photos and videos should be compressed before being sent to the PC.
 *
 *                            <p>Derived from the "Storage Saver" switch in {@code BackupFragment}.
 *                            When {@code true}, the manifest header sent to the PC includes a
 *                            {@code "storage_saver": true} flag so the desktop {@code BackupService}
 *                            knows the incoming images have been down-sampled and can store them
 *                            accordingly. The compression itself is applied by the Android side
 *                            before each file is streamed over the TauSync slot.
 *
 *                            <p>Defaults to {@code false} — full-quality originals are transferred.
 */
public record BackupOptions(boolean classifyImages, int parallelSlots, boolean deleteFilesOnBackup,
                            boolean storageSaver) {

    /**
     * Full constructor.
     *
     * @param classifyImages      {@code true} to ask the PC to run content classification.
     * @param parallelSlots       Number of concurrent TauSync slot channels; clamped to ≥ 1.
     * @param deleteFilesOnBackup {@code true} to delete each source file once the PC
     *                            confirms it was received successfully.
     * @param storageSaver        {@code true} to compress photos and videos before
     *                            transferring them to the PC.
     */
    public BackupOptions(boolean classifyImages, int parallelSlots,
                         boolean deleteFilesOnBackup, boolean storageSaver) {
        this.classifyImages = classifyImages;
        this.parallelSlots = Math.max(1, parallelSlots);
        this.deleteFilesOnBackup = deleteFilesOnBackup;
        this.storageSaver = storageSaver;
    }

    /**
     * Convenience constructor — defaults to {@code storageSaver = false}.
     *
     * @param classifyImages      {@code true} to ask the PC to run content classification.
     * @param parallelSlots       Number of concurrent TauSync slot channels; clamped to ≥ 1.
     * @param deleteFilesOnBackup {@code true} to delete each source file once the PC
     *                            confirms it was received successfully.
     */
    public BackupOptions(boolean classifyImages, int parallelSlots, boolean deleteFilesOnBackup) {
        this(classifyImages, parallelSlots, deleteFilesOnBackup, false);
    }

    /**
     * Convenience constructor — defaults to {@code deleteFilesOnBackup = false}
     * and {@code storageSaver = false}.
     *
     * @param classifyImages {@code true} to ask the PC to run content classification.
     * @param parallelSlots  Number of concurrent TauSync slot channels; clamped to ≥ 1.
     */
    public BackupOptions(boolean classifyImages, int parallelSlots) {
        this(classifyImages, parallelSlots, false, false);
    }

    /**
     * Legacy constructor — defaults to sequential transfer ({@code parallelSlots = 1}),
     * {@code deleteFilesOnBackup = false}, and {@code storageSaver = false}.
     * Keeps existing call sites that do not yet supply a thread count compiling unchanged.
     *
     * @param classifyImages {@code true} to ask the PC to run content classification.
     */
    public BackupOptions(boolean classifyImages) {
        this(classifyImages, 1, false, false);
    }

    /**
     * @return {@code true} if the PC should run image classification on received files.
     */
    @Override
    public boolean classifyImages() {
        return classifyImages;
    }

    /**
     * @return Number of concurrent TauSync slot channels to open during transfer.
     * Always ≥ 1.
     */
    @Override
    public int parallelSlots() {
        return parallelSlots;
    }

    /**
     * @return {@code true} if source files should be deleted once the PC confirms a
     * successful transfer.
     */
    @Override
    public boolean deleteFilesOnBackup() {
        return deleteFilesOnBackup;
    }

    /**
     * @return {@code true} if photos and videos should be compressed before being
     * sent to the PC (Storage Saver mode).
     */
    @Override
    public boolean storageSaver() {
        return storageSaver;
    }

    @Override
    public String toString() {
        return "BackupOptions{classifyImages=" + classifyImages
                + ", parallelSlots=" + parallelSlots
                + ", deleteFilesOnBackup=" + deleteFilesOnBackup
                + ", storageSaver=" + storageSaver + '}';
    }
}
