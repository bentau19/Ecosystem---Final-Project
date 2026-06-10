package com.example.android.domain.entities;

/**
 * User-configured options for a backup operation.
 *
 * <p>Captured in the UI layer ({@link com.example.android.ui.fragments.BackupFragment})
 * when the user taps Start, then carried through the full stack — ViewModel → Repository →
 * {@code ConnectivityService} → {@link com.example.android.domain.usecases.BackupTransferUseCase}
 * — so that the options are included in the manifest header sent to the PC.
 *
 * <p>This is a pure Java class with zero Android Framework dependencies, keeping the
 * domain layer unit-testable without an emulator.
 */
public class BackupOptions {

    /**
     * Whether the PC should run image classification on the received files.
     *
     * <p>Derived from the "Don't classify junk files" checkbox in
     * {@code BackupFragment}: if the checkbox is <b>unchecked</b> (default),
     * {@code classifyImages} is {@code true}; if <b>checked</b>, it is {@code false}.
     */
    private final boolean classifyImages;

    /**
     * Number of file slots to open concurrently on the TauSync transport.
     *
     * <p>Android sends {@code parallelSlots} backup slot channels simultaneously
     * so that storage I/O for one file overlaps with the network transfer of another.
     * The desktop {@code BackupService} already handles parallel slots — it spawns
     * one receiver thread per discovered {@code backup_slot_*} channel, regardless
     * of how many are open at once.
     *
     * <p>Value is clamped to at least 1.  The UI layer computes the default via
     * {@code BackupFragment.computeParallelSlots()} using CPU core count and battery
     * level; the domain layer treats it as an opaque integer.
     */
    private final int parallelSlots;

    /**
     * Whether the source file should be deleted from the device once the PC has
     * confirmed it received and saved the file successfully.
     *
     * <p>Derived from the "Delete originals after backup" checkbox in
     * {@code BackupFragment}. {@link com.example.android.domain.usecases.BackupTransferUseCase}
     * only deletes a file when the PC explicitly reports
     * {@link com.example.android.enums.BackupFileResult#SUCCESS} ("succ") on the
     * corresponding {@code backup_file_result_*} channel — a "fail" result, timeout,
     * or read error never triggers deletion.
     */
    private final boolean deleteFilesOnBackup;

    /**
     * Full constructor.
     *
     * @param classifyImages      {@code true} to ask the PC to run content classification.
     * @param parallelSlots       Number of concurrent TauSync slot channels; clamped to ≥ 1.
     * @param deleteFilesOnBackup {@code true} to delete each source file once the PC
     *                            confirms it was received successfully.
     */
    public BackupOptions(boolean classifyImages, int parallelSlots, boolean deleteFilesOnBackup) {
        this.classifyImages      = classifyImages;
        this.parallelSlots       = Math.max(1, parallelSlots);
        this.deleteFilesOnBackup = deleteFilesOnBackup;
    }

    /**
     * Convenience constructor — defaults to {@code deleteFilesOnBackup = false}.
     *
     * @param classifyImages {@code true} to ask the PC to run content classification.
     * @param parallelSlots  Number of concurrent TauSync slot channels; clamped to ≥ 1.
     */
    public BackupOptions(boolean classifyImages, int parallelSlots) {
        this(classifyImages, parallelSlots, false);
    }

    /**
     * Legacy constructor — defaults to sequential transfer ({@code parallelSlots = 1})
     * and {@code deleteFilesOnBackup = false}.
     * Keeps existing call sites that do not yet supply a thread count compiling unchanged.
     *
     * @param classifyImages {@code true} to ask the PC to run content classification.
     */
    public BackupOptions(boolean classifyImages) {
        this(classifyImages, 1, false);
    }

    /**
     * @return {@code true} if the PC should run image classification on received files.
     */
    public boolean isClassifyImages() {
        return classifyImages;
    }

    /**
     * @return Number of concurrent TauSync slot channels to open during transfer.
     *         Always ≥ 1.
     */
    public int getParallelSlots() {
        return parallelSlots;
    }

    /**
     * @return {@code true} if source files should be deleted once the PC confirms a
     *         successful transfer.
     */
    public boolean isDeleteFilesOnBackup() {
        return deleteFilesOnBackup;
    }

    @Override
    public String toString() {
        return "BackupOptions{classifyImages=" + classifyImages
                + ", parallelSlots=" + parallelSlots
                + ", deleteFilesOnBackup=" + deleteFilesOnBackup + '}';
    }
}
