package com.example.android.ui.fragments;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.DocumentsContract;
import android.provider.MediaStore;
import android.provider.Settings;
import android.util.Log;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.CheckBox;
import android.widget.ImageView;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.appcompat.widget.AppCompatButton;
import androidx.core.content.ContextCompat;
import androidx.documentfile.provider.DocumentFile;
import androidx.fragment.app.Fragment;
import androidx.lifecycle.ViewModelProvider;

import com.example.android.R;
import com.example.android.domain.enums.BackupTransferStatus;
import com.example.android.domain.usecases.ScanBackupFilesUseCase;
import com.example.android.viewmodel.BackupViewModel;
import com.example.android.viewmodel.BackupViewModelFactory;

/**
 * BackupFragment — lets the user configure a backup operation before starting it.
 *
 * <p>Two mutually-exclusive mode cards (radio-like):
 * <ul>
 *   <li>{@code MODE_ALL_MEDIA} — backs up every photo and video on the device.</li>
 *   <li>{@code MODE_FOLDER}    — lets the user choose a specific folder via the
 *       system Storage Access Framework picker.</li>
 * </ul>
 *
 * <p>Folder-mode flow:
 * <ol>
 *   <li>User taps the "Backup Folder Files" card → {@link #REQ_PICK_FOLDER} launched.</li>
 *   <li>User picks a folder in the system UI → {@link #onActivityResult} stores the URI,
 *       updates the card subtitle, and enables the Start button.</li>
 *   <li>User cancels → card stays highlighted but Start remains disabled.</li>
 * </ol>
 *
 * <p>All-media flow:
 * <ol>
 *   <li>User taps "Back Up All Media" → Start is enabled immediately.</li>
 *   <li>User taps Start → permissions are checked/requested at runtime.</li>
 *   <li>Once granted, {@link BackupViewModel#startScan} is called.</li>
 * </ol>
 *
 * <p>Two independent option checkboxes:
 * <ul>
 *   <li>Don't classify junk files</li>
 *   <li>Delete originals after backup</li>
 * </ul>
 *
 * <p>Navigation back to {@link ActionsFragment} is handled by the system back-stack.
 */
public class BackupFragment extends Fragment {

    private static final String TAG = "BackupFragment";

    // ── Mode constants ────────────────────────────────────────────────────────
    private static final String MODE_ALL_MEDIA = ScanBackupFilesUseCase.MODE_ALL_MEDIA;
    private static final String MODE_FOLDER = ScanBackupFilesUseCase.MODE_FOLDER;

    /**
     * Request code for {@link Intent#ACTION_OPEN_DOCUMENT_TREE}.
     */
    private static final int REQ_PICK_FOLDER = 1001;

    /** Request code for runtime media-read permissions. */
    private static final int REQ_MEDIA_PERMISSIONS = 1002;

    /** Request code for the MANAGE_EXTERNAL_STORAGE system settings screen (API 30+). */
    private static final int REQ_ALL_FILES_ACCESS = 1003;

    // ── State ─────────────────────────────────────────────────────────────────
    @Nullable
    private String selectedMode = null;
    @Nullable
    private Uri selectedFolderUri = null;

    // ── ViewModel ─────────────────────────────────────────────────────────────
    private BackupViewModel backupViewModel;

    // ── Views ─────────────────────────────────────────────────────────────────
    private View cardAllMedia;
    private View cardFolder;
    private View dotAllMedia;
    private View dotFolder;
    private TextView tvFolderSubtitle;
    private CheckBox cbNoJunk;
    private CheckBox cbDeleteAfter;
    private AppCompatButton btnStart;
//    private ImageView btnBack;
    /**
     * Shown while SCANNING; hidden otherwise. Null when the layout doesn't include it yet.
     */
    @Nullable
    private ProgressBar pbScanning;

    /**
     * Shows "Sending X / Y files…" during the backup transfer phase.
     * Null when the layout doesn't include it yet (gracefully absent).
     */
    @Nullable
    private TextView tvTransferProgress;

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    @Override
    public View onCreateView(@NonNull LayoutInflater inflater,
                             ViewGroup container,
                             Bundle savedInstanceState) {
        View view = inflater.inflate(R.layout.fragment_backup, container, false);
        bindViews(view);
        initViewModel();
        setupClickListeners();
        observeViewModel();
        return view;
    }

    // ── ViewModel init ────────────────────────────────────────────────────────

    private void initViewModel() {
        backupViewModel = new ViewModelProvider(
                this,
                new BackupViewModelFactory(requireActivity().getApplication())
        ).get(BackupViewModel.class);
    }

    // ── View binding ──────────────────────────────────────────────────────────

    private void bindViews(View root) {
        cardAllMedia = root.findViewById(R.id.cardAllMedia);
        cardFolder = root.findViewById(R.id.cardFolder);
        dotAllMedia = root.findViewById(R.id.dotAllMedia);
        dotFolder = root.findViewById(R.id.dotFolder);
        tvFolderSubtitle = root.findViewById(R.id.tvFolderSubtitle);
        cbNoJunk = root.findViewById(R.id.cbNoJunk);
        cbDeleteAfter = root.findViewById(R.id.cbDeleteAfter);
        btnStart = root.findViewById(R.id.btnStart);

        // pbScanning / tvTransferProgress are optional in the layout — gracefully absent if not added yet
        pbScanning = null;
        tvTransferProgress = null;

    }

    // ── Click listeners ───────────────────────────────────────────────────────

    private void setupClickListeners() {
        cardAllMedia.setOnClickListener(v -> selectMode(MODE_ALL_MEDIA));
        cardFolder.setOnClickListener(v -> selectMode(MODE_FOLDER));
        btnStart.setOnClickListener(v -> onStartBackup());
    }

    // ── ViewModel observers ───────────────────────────────────────────────────

    private void observeViewModel() {
        // ── Scan status ───────────────────────────────────────────────────────
        backupViewModel.getScanStatus().observe(getViewLifecycleOwner(), status -> {
            if (status == null) return;
            Log.d(TAG, "Scan status → " + status);

            switch (status) {
                case SCANNING:
                    // Disable UI while scanning to prevent double-taps
                    btnStart.setEnabled(false);
                    btnStart.setAlpha(0.4f);
                    if (pbScanning != null) pbScanning.setVisibility(View.VISIBLE);
                    break;

                case READY:
                    if (pbScanning != null) pbScanning.setVisibility(View.GONE);
                    // Scan finished — immediately begin the backup transfer.
                    // The scan result list is in the ViewModel; startTransfer() reads it.
                    int count = 0;
                    if (backupViewModel.getScannedFiles().getValue() != null) {
                        count = backupViewModel.getScannedFiles().getValue().size();
                    }
                    Log.d(TAG, "Scan complete: " + count + " files — starting transfer");
                    backupViewModel.reset();          // clear scan state
                    backupViewModel.startTransfer();  // hand off to transfer phase
                    break;

                case FAILED:
                    if (pbScanning != null) pbScanning.setVisibility(View.GONE);
                    restoreStartButton();
                    Toast.makeText(requireContext(),
                            "Scan failed — check permissions and try again",
                            Toast.LENGTH_LONG).show();
                    backupViewModel.reset();
                    break;

                case IDLE:
                default:
                    if (pbScanning != null) pbScanning.setVisibility(View.GONE);
                    break;
            }
        });

        // ── Transfer status ───────────────────────────────────────────────────
        backupViewModel.getTransferStatus().observe(getViewLifecycleOwner(), status -> {
            if (status == null) return;
            Log.d(TAG, "Transfer status → " + status);

            switch (status) {
                case SENDING:
                    // Keep Start button disabled while transfer is in progress.
                    // In-app progress text is driven by getTransferSent() observer below.
                    btnStart.setEnabled(false);
                    btnStart.setAlpha(0.4f);
                    if (tvTransferProgress != null) tvTransferProgress.setVisibility(View.VISIBLE);
                    break;

                case COMPLETED: {
                    if (tvTransferProgress != null) tvTransferProgress.setVisibility(View.GONE);
                    restoreStartButton();
                    Integer total = backupViewModel.getTransferTotal().getValue();
                    int t = (total != null) ? total : 0;
                    Toast.makeText(requireContext(),
                            "Backup complete! " + t + " files sent",
                            Toast.LENGTH_LONG).show();
                    backupViewModel.resetTransfer();
                    break;
                }

                case FAILED:
                    if (tvTransferProgress != null) tvTransferProgress.setVisibility(View.GONE);
                    restoreStartButton();
                    Toast.makeText(requireContext(),
                            "Backup transfer failed — check your connection",
                            Toast.LENGTH_LONG).show();
                    backupViewModel.resetTransfer();
                    break;

                case IDLE:
                default:
                    if (tvTransferProgress != null) tvTransferProgress.setVisibility(View.GONE);
                    break;
            }
        });

        // ── Transfer progress counter — updates the in-app "X / Y files" text ──
        backupViewModel.getTransferSent().observe(getViewLifecycleOwner(), sent -> {
            if (tvTransferProgress == null) return;
            Integer total = backupViewModel.getTransferTotal().getValue();
            int s = (sent  != null) ? sent  : 0;
            int t = (total != null) ? total : 0;
            tvTransferProgress.setText("Sending " + s + " / " + t + " files…");
        });
    }

    // ── Selection logic ───────────────────────────────────────────────────────

    /**
     * Highlights the chosen card with a cyan stroke and dims the other one.
     *
     * <p>For {@code MODE_ALL_MEDIA}: enables Start Backup immediately.
     * <p>For {@code MODE_FOLDER}: keeps Start Backup <em>disabled</em> until
     * the user confirms a folder in {@link #onActivityResult}.
     *
     * @param mode one of {@link #MODE_ALL_MEDIA} or {@link #MODE_FOLDER}
     */
    private void selectMode(String mode) {
        selectedMode = mode;

        // Reset both cards to the default (unselected) drawable
        cardAllMedia.setBackgroundResource(R.drawable.backup_card_default);
        cardFolder.setBackgroundResource(R.drawable.backup_card_default);
        dotAllMedia.setVisibility(View.GONE);
        dotFolder.setVisibility(View.GONE);

        if (MODE_ALL_MEDIA.equals(mode)) {
            cardAllMedia.setBackgroundResource(R.drawable.backup_card_selected);
            dotAllMedia.setVisibility(View.VISIBLE);

            selectedFolderUri = null;
            tvFolderSubtitle.setText(R.string.backup_btn_folder_sub);

            btnStart.setEnabled(true);
            btnStart.setAlpha(1.0f);

        } else { // MODE_FOLDER
            cardFolder.setBackgroundResource(R.drawable.backup_card_selected);
            dotFolder.setVisibility(View.VISIBLE);

            if (selectedFolderUri == null) {
                btnStart.setEnabled(false);
                btnStart.setAlpha(0.4f);
            }

            launchFolderPicker();
        }
    }

    // ── Folder picker launch ──────────────────────────────────────────────────

    /**
     * Shows an explanatory dialog about Android's folder-picker restrictions, then
     * launches {@link Intent#ACTION_OPEN_DOCUMENT_TREE} with an {@code EXTRA_INITIAL_URI}
     * hint so the picker opens inside external media (DCIM area) rather than at the
     * blocked storage root.
     *
     * <p>Android 11+ (API 30+) prevents the user from selecting certain top-level
     * directories — the storage root, Downloads, and SD card root — via
     * {@code ACTION_OPEN_DOCUMENT_TREE}. Attempting to confirm such a directory causes
     * Android to display its own "Can't use this folder for privacy reasons" system
     * dialog. This pre-warning sets expectations before the picker opens.
     *
     * <p>If the user cancels this dialog (before the picker even opens), the folder card
     * is de-selected and {@code selectedMode} is reset to {@code null} so the fragment
     * stays in a consistent state.
     */
    private void launchFolderPicker() {
        new AlertDialog.Builder(requireContext())
                .setTitle("Choose a Specific Subfolder")
                .setMessage(
                        "Android restricts access to the root of your storage and the "
                        + "Downloads folder.\n\n"
                        + "Please pick a specific subfolder instead — for example:\n"
                        + "  • DCIM/Camera\n"
                        + "  • Pictures/WhatsApp\n"
                        + "  • Movies/Telegram\n\n"
                        + "If you see \"Can't use this folder\", navigate into a subfolder "
                        + "and try again.")
                .setPositiveButton("Choose Folder", (d, w) -> {
                    Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
                    // API 26+: hint the picker to open inside external media so the user
                    // starts in a valid location rather than the blocked storage root.
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        intent.putExtra(DocumentsContract.EXTRA_INITIAL_URI,
                                MediaStore.Images.Media.EXTERNAL_CONTENT_URI);
                    }
                    startActivityForResult(intent, REQ_PICK_FOLDER);
                })
                .setNegativeButton("Cancel", (d, w) -> {
                    // User bailed before opening the picker — reset card state so the
                    // fragment is consistent (no mode selected, no card highlighted).
                    selectedMode = null;
                    cardFolder.setBackgroundResource(R.drawable.backup_card_default);
                    dotFolder.setVisibility(View.GONE);
                    if (selectedFolderUri == null) {
                        btnStart.setEnabled(false);
                        btnStart.setAlpha(0.4f);
                    }
                })
                .setCancelable(false)
                .show();
    }

    // ── Folder picker result ──────────────────────────────────────────────────

    @Override
    public void onActivityResult(int requestCode, int resultCode, @Nullable Intent data) {
        super.onActivityResult(requestCode, resultCode, data);

        // ── All-files access settings returned ────────────────────────────────
        if (requestCode == REQ_ALL_FILES_ACCESS) {
            // The settings screen doesn't return a meaningful resultCode — check the
            // actual permission state instead. Either way, proceed with the scan
            // (Android/data/ walk is only performed when the permission is held).
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R
                    && Environment.isExternalStorageManager()) {
                Log.d(TAG, "All Files Access granted — Android/data/ will be included");
            } else {
                Log.d(TAG, "All Files Access not granted — scan proceeds without Android/data/");
            }
            startScan();
            return;
        }

        if (requestCode != REQ_PICK_FOLDER) return;

        if (resultCode != Activity.RESULT_OK || data == null) {
            return;
        }

        Uri uri = data.getData();
        if (uri == null) return;

        final int persistFlags = Intent.FLAG_GRANT_READ_URI_PERMISSION
                | Intent.FLAG_GRANT_WRITE_URI_PERMISSION;
        requireActivity().getContentResolver()
                .takePersistableUriPermission(uri, persistFlags);

        selectedFolderUri = uri;

        DocumentFile dir = DocumentFile.fromTreeUri(requireContext(), uri);
        String folderName = (dir != null && dir.getName() != null)
                ? dir.getName()
                : uri.getLastPathSegment();

        tvFolderSubtitle.setText(
                getString(R.string.backup_folder_selected_prefix) + folderName);

        btnStart.setEnabled(true);
        btnStart.setAlpha(1.0f);
    }

    // ── Start action ──────────────────────────────────────────────────────────

    /**
     * Invoked when the user taps Start Backup.
     *
     * <p>For {@code MODE_ALL_MEDIA}: checks/requests runtime media permissions before
     * starting the scan.
     * <p>For {@code MODE_FOLDER}: the SAF URI already carries an implicit grant, so
     * the scan starts immediately.
     */
    private void onStartBackup() {
        if (selectedMode == null) {
            Toast.makeText(requireContext(), "Please select a backup mode", Toast.LENGTH_SHORT).show();
            return;
        }

        if (MODE_ALL_MEDIA.equals(selectedMode)) {
            if (hasMediaPermissions()) {
                // Media access granted — optionally offer full filesystem access next
                checkAllFilesAccessThenScan();
            } else {
                requestMediaPermissions();
            }
        } else {
            // Folder mode — SAF grant is implicit; start immediately
            startScan();
        }
    }

    // ── Permission handling ───────────────────────────────────────────────────

    /**
     * Returns {@code true} if the app holds enough media-read permission to proceed.
     *
     * <ul>
     *   <li>API 34+: full ({@code READ_MEDIA_IMAGES + READ_MEDIA_VIDEO}) OR
     *       partial ({@code READ_MEDIA_VISUAL_USER_SELECTED}) — either allows the scan.</li>
     *   <li>API 33: needs {@code READ_MEDIA_IMAGES + READ_MEDIA_VIDEO}.</li>
     *   <li>API 24–32: needs {@code READ_EXTERNAL_STORAGE}.</li>
     * </ul>
     */
    private boolean hasMediaPermissions() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) { // API 34+
            boolean full =
                    ContextCompat.checkSelfPermission(requireContext(),
                            Manifest.permission.READ_MEDIA_IMAGES) == PackageManager.PERMISSION_GRANTED
                    && ContextCompat.checkSelfPermission(requireContext(),
                            Manifest.permission.READ_MEDIA_VIDEO) == PackageManager.PERMISSION_GRANTED;
            boolean partial =
                    ContextCompat.checkSelfPermission(requireContext(),
                            Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED) == PackageManager.PERMISSION_GRANTED;
            return full || partial;
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) { // API 33
            return ContextCompat.checkSelfPermission(requireContext(),
                    Manifest.permission.READ_MEDIA_IMAGES) == PackageManager.PERMISSION_GRANTED
                    && ContextCompat.checkSelfPermission(requireContext(),
                    Manifest.permission.READ_MEDIA_VIDEO) == PackageManager.PERMISSION_GRANTED;
        } else { // API 24–32
            return ContextCompat.checkSelfPermission(requireContext(),
                    Manifest.permission.READ_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED;
        }
    }

    private void requestMediaPermissions() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) { // API 34+
            requestPermissions(new String[]{
                    Manifest.permission.READ_MEDIA_IMAGES,
                    Manifest.permission.READ_MEDIA_VIDEO,
                    Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED
            }, REQ_MEDIA_PERMISSIONS);
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) { // API 33
            requestPermissions(new String[]{
                    Manifest.permission.READ_MEDIA_IMAGES,
                    Manifest.permission.READ_MEDIA_VIDEO
            }, REQ_MEDIA_PERMISSIONS);
        } else { // API 24–32
            requestPermissions(new String[]{
                    Manifest.permission.READ_EXTERNAL_STORAGE
            }, REQ_MEDIA_PERMISSIONS);
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode,
                                           @NonNull String[] permissions,
                                           @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != REQ_MEDIA_PERMISSIONS) return;

        if (hasMediaPermissions()) {
            checkAllFilesAccessThenScan();
        } else {
            Toast.makeText(requireContext(),
                    "Media access is required for all-media backup",
                    Toast.LENGTH_LONG).show();
        }
    }

    // ── All-files access (MANAGE_EXTERNAL_STORAGE) ───────────────────────────

    /**
     * Called once media permissions are confirmed.
     *
     * <p>On API 30+, offers the user a chance to also grant
     * {@code MANAGE_EXTERNAL_STORAGE} so that private app directories like
     * {@code Android/data/com.whatsapp/…/Private/} are included in the scan.
     * The scan is <b>never blocked</b> on this — "Skip" proceeds immediately with
     * MediaStore results only.
     *
     * <p>On API 29 and below, calls {@link #startScan()} directly.
     */
    private void checkAllFilesAccessThenScan() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            // Android 10 and below: File API already has full access; no extra step needed.
            startScan();
            return;
        }

        if (Environment.isExternalStorageManager()) {
            // Already granted — scan immediately (includes Android/data/ walk).
            startScan();
            return;
        }

        // Not yet granted — offer it non-blocking
        new AlertDialog.Builder(requireContext())
                .setTitle("Include private app media?")
                .setMessage(
                        "Grant \"All Files Access\" to also back up private media folders "
                        + "(e.g. WhatsApp Private, Telegram cache).\n\n"
                        + "Tap Skip to back up regular photos and videos only.")
                .setPositiveButton("Grant access", (d, w) -> openAllFilesAccessSettings())
                .setNegativeButton("Skip", (d, w) -> startScan())
                .setCancelable(false)
                .show();
    }

    /** Opens the system All Files Access settings screen for this app. */
    private void openAllFilesAccessSettings() {
        try {
            Intent intent = new Intent(
                    Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                    Uri.parse("package:" + requireContext().getPackageName()));
            startActivityForResult(intent, REQ_ALL_FILES_ACCESS);
        } catch (Exception e) {
            // Some OEMs don't expose the per-app screen — fall back to the generic one
            Log.w(TAG, "Per-app all-files screen unavailable, opening generic screen");
            startActivityForResult(
                    new Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION),
                    REQ_ALL_FILES_ACCESS);
        }
    }

    // ── Scan dispatch ─────────────────────────────────────────────────────────

    /**
     * Passes the current configuration to the ViewModel and triggers the scan.
     * The ViewModel spawns a background thread; results arrive via LiveData.
     */
    private void startScan() {
        boolean noJunk = cbNoJunk.isChecked();
        boolean deleteAfter = cbDeleteAfter.isChecked();
        Log.d(TAG, "startScan: mode=" + selectedMode
                + " noJunk=" + noJunk + " deleteAfter=" + deleteAfter);
        // noJunk / deleteAfter are options for a later phase (manifest + transfer).
        // For now they are logged and will be passed through once the BackupOptions
        // entity is wired end-to-end.
        backupViewModel.startScan(selectedMode, selectedFolderUri);
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    /**
     * Re-enables the Start button after a terminal scan state.
     */
    private void restoreStartButton() {
        // Only re-enable if a valid mode is still selected
        boolean canStart = selectedMode != null
                && (MODE_ALL_MEDIA.equals(selectedMode)
                || (MODE_FOLDER.equals(selectedMode) && selectedFolderUri != null));
        btnStart.setEnabled(canStart);
        btnStart.setAlpha(canStart ? 1.0f : 0.4f);
    }
}
