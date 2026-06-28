package com.example.android.ui.fragments;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.BatteryManager;
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
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.widget.SwitchCompat;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.File;
import androidx.appcompat.widget.AppCompatButton;
import androidx.core.content.ContextCompat;
import androidx.documentfile.provider.DocumentFile;
import androidx.fragment.app.Fragment;
import androidx.lifecycle.ViewModelProvider;

import com.example.android.domain.enums.BackupScanStatus;
import com.example.android.domain.enums.BackupTransferStatus;

import com.example.android.R;
import com.example.android.domain.entities.BackupOptions;
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
 *   <li>User taps the "Backup Folder Files" card → {@link #launchFolderPicker()} invoked.</li>
 *   <li><b>API 30+ with MANAGE_EXTERNAL_STORAGE</b> (or API 24–29 with READ_EXTERNAL_STORAGE):
 *       {@link FolderPickerFragment} opens — a custom File-API browser with no SAF
 *       restrictions.  Downloads, DCIM root, and other top-level directories are selectable.</li>
 *   <li><b>API 30+ without MANAGE_EXTERNAL_STORAGE</b>: a dialog offers to grant the
 *       permission first; the user can skip to the system SAF picker (Downloads unavailable).</li>
 *   <li>On folder confirmed → {@code selectedFolderUri} is set to a {@code file://} URI,
 *       the card subtitle updates, and the Start button is enabled.</li>
 *   <li>User cancels → card resets to unselected state if no prior selection existed.</li>
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
 * <p><b>Start &amp; return-to-main flow:</b> tapping Start Backup hands the scan off to
 * {@link BackupViewModel#startScan} and immediately pops this fragment off the back
 * stack, returning to {@link ActionsFragment}. There is no in-app progress UI — the
 * scan→transfer handoff is owned by {@code BackupRepository} (auto-triggers the
 * transfer once the scan completes) and all progress / pause / resume / stop /
 * completion feedback is delivered exclusively via the sticky
 * {@code BackupProgressChannel} notification (see {@code AppNotificationManager}
 * and {@code ConnectivityService}).
 *
 * <p>Navigation back to {@link ActionsFragment} is handled by the system back-stack
 * (popped programmatically on Start, or by the user via the back button beforehand).
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

    /**
     * Separate request code used when the user opens the All Files Access settings
     * specifically to enable the custom folder picker (not the all-media scan flow).
     * Keeps the two return paths distinct in {@link #onActivityResult}.
     */
    private static final int REQ_ALL_FILES_ACCESS_FOR_PICKER = 1004;

    // ── State ─────────────────────────────────────────────────────────────────
    @Nullable
    private String selectedMode = null;
    @Nullable
    private Uri selectedFolderUri = null;

    /**
     * Set to {@code true} just before {@link BackupViewModel#startScan} is called,
     * cleared when the scan-status observer handles a terminal state (IDLE/EMPTY/FAILED).
     * Guards the IDLE-observer branch so we can distinguish "scan completed with files"
     * from the initial IDLE state the repository starts in.
     */
    private boolean scanInProgress = false;

    /**
     * Set to {@code true} when the scan completes successfully and the transfer has been
     * dispatched.  Cleared by the transfer-status observer when a terminal state arrives
     * (COMPLETED / FAILED / STOPPED).
     *
     * <p>Guards the {@code transferStatus} observer so it ignores the initial IDLE value
     * emitted at registration time and the IDLE that follows {@code resetTransfer()}.
     */
    private boolean transferInProgress = false;

    // ── ViewModel ─────────────────────────────────────────────────────────────
    private BackupViewModel backupViewModel;

    // ── Views ─────────────────────────────────────────────────────────────────
    private View cardAllMedia;
    private View cardFolder;
    private View dotAllMedia;
    private View dotFolder;
    private TextView tvFolderSubtitle;
    private CheckBox cbClassify;
    private CheckBox cbDeleteAfter;
    private SwitchCompat switchStorageSaver;
    private TextView tvStorageSaverState;
    private View cardStorageSaver;
    private AppCompatButton btnStart;
    private View btnBack;

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    @Override
    public View onCreateView(@NonNull LayoutInflater inflater,
                             ViewGroup container,
                             Bundle savedInstanceState) {
        View view = inflater.inflate(R.layout.fragment_backup, container, false);
        bindViews(view);
        setupClickListeners();
        return view;
    }

    @Override
    public void onViewCreated(@NonNull View view, @Nullable Bundle savedInstanceState) {
        super.onViewCreated(view, savedInstanceState);
        initViewModel();
        // Observe scan lifecycle — drives loading state, error dialogs, and navigation.
        backupViewModel.getScanStatus().observe(getViewLifecycleOwner(),
                this::onScanStatusChanged);
        // Observe transfer lifecycle — keeps the fragment alive until the summary dialog
        // is shown and acknowledged, rather than popping immediately after scan completes.
        backupViewModel.getTransferStatus().observe(getViewLifecycleOwner(),
                this::onTransferStatusChanged);
        // Observe per-file progress ticks to update the in-progress button label.
        backupViewModel.getTransferSent().observe(getViewLifecycleOwner(),
                this::onTransferSentChanged);
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
        cbClassify = root.findViewById(R.id.cbClassify);
        cbDeleteAfter = root.findViewById(R.id.cbDeleteAfter);
        switchStorageSaver = root.findViewById(R.id.switchStorageSaver);
        tvStorageSaverState = root.findViewById(R.id.tvStorageSaverState);
        cardStorageSaver = root.findViewById(R.id.cardStorageSaver);
        btnStart = root.findViewById(R.id.btnStart);
        btnBack  = root.findViewById(R.id.btnBack);
    }

    // ── Click listeners ───────────────────────────────────────────────────────

    private void setupClickListeners() {
        btnBack.setOnClickListener(v ->
                requireActivity().getSupportFragmentManager().popBackStack());
        cardAllMedia.setOnClickListener(v -> selectMode(MODE_ALL_MEDIA));
        cardFolder.setOnClickListener(v -> selectMode(MODE_FOLDER));
        btnStart.setOnClickListener(v -> onStartBackup());
        setupStorageSaverToggle();
    }

    /**
     * Wires the Storage Saver switch to two reinforcing visual state signals:
     *
     * <ol>
     *   <li><b>State label</b> ({@code tvStorageSaverState}): text flips between
     *       "OFF" ({@code text_muted} grey) and "ON" ({@code accent_cyan} blue),
     *       giving an unambiguous text confirmation of the current state.</li>
     *   <li><b>Card border</b> ({@code cardStorageSaver}): swaps between
     *       {@code backup_card_default} (dim 1dp border) and
     *       {@code backup_card_selected} (2dp cyan stroke) — the same visual
     *       language used by the mode-selection cards above.</li>
     * </ol>
     */
    private void setupStorageSaverToggle() {
        switchStorageSaver.setOnCheckedChangeListener((btn, isChecked) -> {
            // Update the "OFF" / "ON" label text and colour
            tvStorageSaverState.setText(isChecked
                    ? R.string.backup_opt_storage_saver_on
                    : R.string.backup_opt_storage_saver_off);
            tvStorageSaverState.setTextColor(ContextCompat.getColor(requireContext(),
                    isChecked ? R.color.accent_cyan : R.color.text_muted));

            // Update the card border (same drawable swap the mode cards use)
            cardStorageSaver.setBackgroundResource(isChecked
                    ? R.drawable.backup_card_selected
                    : R.drawable.backup_card_default);
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
     * Entry point when the user selects "Backup Folder Files".
     *
     * <p>Decision tree:
     * <ul>
     *   <li><b>API 30+ with {@code MANAGE_EXTERNAL_STORAGE}</b>: opens the custom
     *       {@link FolderPickerFragment} — no SAF restrictions, Downloads selectable.</li>
     *   <li><b>API 30+ without {@code MANAGE_EXTERNAL_STORAGE}</b>: shows a dialog
     *       offering to grant access; user can grant (→ settings → return → custom picker)
     *       or skip (→ SAF picker with original restrictions).</li>
     *   <li><b>API 24–29 with {@code READ_EXTERNAL_STORAGE}</b>: opens the custom picker
     *       directly — scoped storage restrictions do not apply on these API levels.</li>
     *   <li><b>API 24–29 without {@code READ_EXTERNAL_STORAGE}</b>: falls back to the SAF
     *       picker (the permission check is lenient on older API levels).</li>
     * </ul>
     */
    private void launchFolderPicker() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            // ── API 30+: check MANAGE_EXTERNAL_STORAGE ────────────────────────
            if (Environment.isExternalStorageManager()) {
                openCustomPicker();
            } else {
                showGrantStorageAccessDialog();
            }
        } else {
            // ── API 24–29: READ_EXTERNAL_STORAGE gives full File API access ───
            boolean hasReadStorage = ContextCompat.checkSelfPermission(
                    requireContext(), Manifest.permission.READ_EXTERNAL_STORAGE)
                    == PackageManager.PERMISSION_GRANTED;
            if (hasReadStorage) {
                openCustomPicker();
            } else {
                // Permission not held yet — fall back to the SAF picker which works
                // without READ_EXTERNAL_STORAGE (SAF uses its own URI grants).
                openSafPicker();
            }
        }
    }

    /**
     * Shows the in-app {@link FolderPickerFragment} — a {@link
     * com.google.android.material.bottomsheet.BottomSheetDialogFragment} that uses
     * the {@link File} API.  No SAF restrictions apply, so the user can pick
     * Downloads, DCIM root, storage root, or any other readable directory.
     */
    private void openCustomPicker() {
        FolderPickerFragment picker = FolderPickerFragment.newInstance(
                Environment.getExternalStorageDirectory());
        picker.setCallback(new FolderPickerFragment.FolderSelectedCallback() {
            @Override
            public void onFolderSelected(@NonNull File folder) {
                // file:// URI — ScanBackupFilesUseCase detects the scheme and routes
                // to BackupDataSource.scanFolderByPath() instead of scanFolder().
                selectedFolderUri = Uri.fromFile(folder);
                tvFolderSubtitle.setText(
                        getString(R.string.backup_folder_selected_prefix) + folder.getName());
                btnStart.setEnabled(true);
                btnStart.setAlpha(1.0f);
            }

            @Override
            public void onPickerCancelled() {
                // Reset folder card only if no folder was previously confirmed.
                if (selectedFolderUri == null) {
                    selectedMode = null;
                    cardFolder.setBackgroundResource(R.drawable.backup_card_default);
                    dotFolder.setVisibility(View.GONE);
                    btnStart.setEnabled(false);
                    btnStart.setAlpha(0.4f);
                }
            }
        });
        picker.show(getChildFragmentManager(), "folder_picker");
    }

    /**
     * Shown on API 30+ when {@code MANAGE_EXTERNAL_STORAGE} is not yet granted.
     * Gives the user two options:
     * <ul>
     *   <li><b>Grant Access</b>: opens the system All Files Access settings screen.
     *       On return, if the permission was granted the custom picker opens; if not,
     *       the SAF picker is shown as a fallback.</li>
     *   <li><b>Skip</b>: opens the SAF picker immediately (Downloads will be
     *       unavailable due to Android OS restriction).</li>
     * </ul>
     */
    private void showGrantStorageAccessDialog() {
        new AlertDialog.Builder(requireContext())
                .setTitle(R.string.folder_picker_grant_title)
                .setMessage(R.string.folder_picker_grant_msg)
                .setPositiveButton(R.string.folder_picker_grant_positive,
                        (d, w) -> openAllFilesAccessSettingsForPicker())
                .setNegativeButton(R.string.folder_picker_grant_negative,
                        (d, w) -> openSafPicker())
                .setOnCancelListener(d -> resetFolderCardIfNoSelection())
                .setCancelable(true)
                .show();
    }

    /**
     * Opens the system All Files Access settings screen so the user can grant
     * {@code MANAGE_EXTERNAL_STORAGE}.  Uses {@link #REQ_ALL_FILES_ACCESS_FOR_PICKER}
     * so that {@link #onActivityResult} knows to open the custom picker on return
     * (rather than starting the scan, which is what {@link #REQ_ALL_FILES_ACCESS} does).
     */
    private void openAllFilesAccessSettingsForPicker() {
        try {
            Intent intent = new Intent(
                    Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                    Uri.parse("package:" + requireContext().getPackageName()));
            startActivityForResult(intent, REQ_ALL_FILES_ACCESS_FOR_PICKER);
        } catch (Exception e) {
            Log.w(TAG, "Per-app all-files screen unavailable, opening generic screen");
            startActivityForResult(
                    new Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION),
                    REQ_ALL_FILES_ACCESS_FOR_PICKER);
        }
    }

    /**
     * Opens {@link Intent#ACTION_OPEN_DOCUMENT_TREE} — the system SAF picker.
     *
     * <p>Used as a fallback when {@code MANAGE_EXTERNAL_STORAGE} is not granted.
     * On API 30+, the user will NOT be able to select Downloads or other top-level
     * restricted directories (Android OS limitation).
     */
    private void openSafPicker() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        // API 26+: hint the picker to open inside external media so the user
        // starts in a valid location rather than the blocked storage root.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            intent.putExtra(DocumentsContract.EXTRA_INITIAL_URI,
                    MediaStore.Images.Media.EXTERNAL_CONTENT_URI);
        }
        startActivityForResult(intent, REQ_PICK_FOLDER);
    }

    /** Resets the folder card to unselected state if no folder was confirmed yet. */
    private void resetFolderCardIfNoSelection() {
        if (selectedFolderUri == null) {
            selectedMode = null;
            cardFolder.setBackgroundResource(R.drawable.backup_card_default);
            dotFolder.setVisibility(View.GONE);
            btnStart.setEnabled(false);
            btnStart.setAlpha(0.4f);
        }
    }

    // ── Folder picker result ──────────────────────────────────────────────────

    @Override
    public void onActivityResult(int requestCode, int resultCode, @Nullable Intent data) {
        super.onActivityResult(requestCode, resultCode, data);

        // ── All-files access settings returned (all-media scan path) ─────────
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

        // ── All-files access settings returned (folder picker path) ──────────
        if (requestCode == REQ_ALL_FILES_ACCESS_FOR_PICKER) {
            // Returned from settings after the user tapped "Grant Access" in
            // showGrantStorageAccessDialog().  If permission was granted, open the
            // custom picker; otherwise fall back to the SAF picker.
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R
                    && Environment.isExternalStorageManager()) {
                Log.d(TAG, "All Files Access granted — opening custom folder picker");
                openCustomPicker();
            } else {
                Log.d(TAG, "All Files Access not granted — falling back to SAF picker");
                openSafPicker();
            }
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
     *
     * <p>Unlike the previous "fire-and-forget" approach, the Fragment now stays
     * alive and observes {@link BackupViewModel#getScanStatus()} until a terminal
     * state arrives:
     * <ul>
     *   <li>{@link BackupScanStatus#IDLE} (after a successful scan with files) →
     *       toast + popBackStack.</li>
     *   <li>{@link BackupScanStatus#EMPTY} → mode-specific error dialog; user
     *       stays on BackupFragment to pick a different source.</li>
     *   <li>{@link BackupScanStatus#FAILED} → generic error dialog.</li>
     * </ul>
     *
     * <p>The scan→transfer handoff and all progress/completion feedback from this
     * point on are owned by {@code BackupRepository} and {@code ConnectivityService}
     * (sticky {@code BackupProgressChannel} notification).
     */
    private void startScan() {
        // "Classify junk files" checked (default) → classify_images = true
        boolean classifyImages = cbClassify.isChecked();
        boolean deleteAfter    = cbDeleteAfter.isChecked();
        boolean storageSaver   = switchStorageSaver.isChecked();
        int     parallelSlots  = computeParallelSlots();
        Log.d(TAG, "startScan: mode=" + selectedMode
                + " classifyImages=" + classifyImages
                + " deleteAfter=" + deleteAfter
                + " storageSaver=" + storageSaver
                + " parallelSlots=" + parallelSlots);
        BackupOptions options = new BackupOptions(classifyImages, parallelSlots, deleteAfter, storageSaver);

        // Arm the observer guard before dispatching — the background thread may
        // complete and post a new status before the next UI frame.
        scanInProgress = true;
        backupViewModel.startScan(selectedMode, selectedFolderUri, options);
        // Navigation + toast are now handled in onScanStatusChanged().
    }

    // ── Scan status observer ──────────────────────────────────────────────────

    /**
     * Reacts to every scan lifecycle transition posted by {@link BackupRepository}.
     *
     * <p>Only the states that matter to this Fragment are handled:
     * <ul>
     *   <li>{@link BackupScanStatus#SCANNING} — disables UI while the background
     *       thread is running.</li>
     *   <li>{@link BackupScanStatus#IDLE} — if {@link #scanInProgress} is set, the
     *       scan just completed with files (&gt; 0); navigate away.</li>
     *   <li>{@link BackupScanStatus#EMPTY} — zero files found; show a mode-specific
     *       dialog and let the user change their selection.</li>
     *   <li>{@link BackupScanStatus#FAILED} — scan threw an exception; show a
     *       generic error dialog.</li>
     * </ul>
     */
    private void onScanStatusChanged(BackupScanStatus status) {
        if (status == null) return;
        switch (status) {
            case SCANNING:
                setScanningUiState(true);
                break;

            case IDLE:
                // IDLE is the initial state AND the post-success state.
                // Only act when we armed the flag in startScan().
                if (scanInProgress) {
                    scanInProgress = false;
                    setScanningUiState(false);
                    // Scan completed with files — the transfer has been dispatched by
                    // BackupRepository.onScanComplete().  Instead of popping immediately,
                    // stay on this fragment so we can show the in-app summary dialog when
                    // the transfer finishes.
                    transferInProgress = true;
                    setTransferUiState(true, 0, 0);
                }
                break;

            case EMPTY:
                scanInProgress = false;
                transferInProgress = false;
                setTransferUiState(false, 0, 0);
                setScanningUiState(false);
                showEmptyFilesDialog();
                break;

            case FAILED:
                scanInProgress = false;
                setScanningUiState(false);
                showScanFailedDialog();
                break;

            default:
                break;
        }
    }

    /**
     * Toggles the "scanning in progress" UI state on the Start button and the
     * mode-selection cards.
     *
     * @param scanning {@code true} while a scan is running; {@code false} otherwise.
     */
    private void setScanningUiState(boolean scanning) {
        btnStart.setEnabled(!scanning);
        btnStart.setAlpha(scanning ? 0.6f : 1.0f);
        btnStart.setText(scanning ? R.string.backup_scanning : R.string.backup_start);
        // Prevent mode changes mid-scan
        cardAllMedia.setClickable(!scanning);
        cardFolder.setClickable(!scanning);
    }

    /**
     * Shows an AlertDialog whose message depends on the current backup mode:
     * <ul>
     *   <li>{@link #MODE_ALL_MEDIA} → "No photos or videos were found…"</li>
     *   <li>{@link #MODE_FOLDER}    → "No files were found in the selected folder."</li>
     * </ul>
     * The user dismisses the dialog and remains on BackupFragment to pick a
     * different source.
     */
    private void showEmptyFilesDialog() {
        if (!isAdded()) return;
        boolean isAllMedia = MODE_ALL_MEDIA.equals(selectedMode);
        new AlertDialog.Builder(requireContext())
                .setTitle(R.string.backup_error_no_files_title)
                .setMessage(isAllMedia
                        ? R.string.backup_error_no_media
                        : R.string.backup_error_no_folder_files)
                .setPositiveButton(android.R.string.ok, null)
                .show();
    }

    /**
     * Shows a generic "scan failed" dialog (e.g. I/O error or missing permissions).
     */
    private void showScanFailedDialog() {
        if (!isAdded()) return;
        new AlertDialog.Builder(requireContext())
                .setTitle(R.string.backup_error_scan_failed_title)
                .setMessage(R.string.backup_error_scan_failed_msg)
                .setPositiveButton(android.R.string.ok, null)
                .show();
    }

    // ── Transfer phase observers ──────────────────────────────────────────────

    /**
     * Reacts to every transfer lifecycle transition posted by {@link BackupRepository}.
     *
     * <p>The {@link #transferInProgress} guard prevents reacting to:
     * <ul>
     *   <li>The initial IDLE value emitted when the observer is first registered.</li>
     *   <li>The IDLE emitted by {@code ConnectivityService} calling
     *       {@code BackupRepository.resetTransfer()} after COMPLETED.</li>
     * </ul>
     *
     * <p>LiveData dispatch order guarantees that when COMPLETED is posted,
     * {@code ConnectivityService}'s observer (registered first) fires before this one.
     * Even though {@code ConnectivityService} calls {@code resetTransfer()} inside its
     * callback, those {@code postValue()} calls are queued for the <em>next</em>
     * Looper iteration — so {@code failedCount} and {@code transferTotal} are still
     * their pre-reset values when this callback reads them.
     */
    private void onTransferStatusChanged(BackupTransferStatus status) {
        if (!transferInProgress || status == null) return;
        switch (status) {
            case SENDING:
                // Progress ticks are handled by onTransferSentChanged below.
                break;

            case PAUSED:
                // Show "Paused" in the button — the user can resume via the notification.
                btnStart.setText(R.string.backup_scanning); // reuse existing "Scanning…" label
                break;

            case COMPLETED:
                transferInProgress = false;
                setTransferUiState(false, 0, 0);
                showTransferSummaryDialog();
                break;

            case FAILED:
                transferInProgress = false;
                setTransferUiState(false, 0, 0);
                showTransferFailedDialog();
                break;

            case CANCELED_BY_PC:
                // PC dismissed its folder-picker before any file was sent.
                // Stay on BackupFragment — the user should be able to retry immediately.
                transferInProgress = false;
                setTransferUiState(false, 0, 0);
                // Re-enable Start so the user can kick off a new backup right away.
                if (selectedMode != null) {
                    btnStart.setEnabled(true);
                    btnStart.setAlpha(1.0f);
                }
                btnStart.setText(R.string.backup_start);
                if (isAdded()) {
                    Toast.makeText(requireContext(),
                            R.string.backup_canceled_by_pc,
                            Toast.LENGTH_SHORT).show();
                }
                break;

            case STOPPED:
                // User tapped Stop in the notification mid-transfer — pop back to
                // ActionsFragment silently; the notification banner already gave feedback.
                transferInProgress = false;
                setTransferUiState(false, 0, 0);
                if (isAdded()) {
                    requireActivity().getSupportFragmentManager().popBackStack();
                }
                break;

            default:
                break;
        }
    }

    /**
     * Updates the button label with the running progress counter whenever the PC
     * confirms another file ("Backing up X / Y…").
     */
    private void onTransferSentChanged(Integer sent) {
        if (!transferInProgress) return;
        Integer total = backupViewModel.getTransferTotal().getValue();
        int s = (sent  != null) ? sent  : 0;
        int t = (total != null) ? total : 0;
        setTransferUiState(true, s, t);
    }

    // ── Transfer UI state ─────────────────────────────────────────────────────

    /**
     * Locks / unlocks the entire configuration UI while a transfer is in progress.
     *
     * <p>When {@code inProgress} is {@code true}:
     * <ul>
     *   <li>The Start button is disabled and shows "Backing up X / Y…" (or "Scanning…"
     *       while the total is not yet known).</li>
     *   <li>Both mode cards and all option controls are made non-interactive so the user
     *       cannot change the configuration mid-transfer.</li>
     * </ul>
     *
     * @param inProgress {@code true} while transfer is running; {@code false} to restore.
     * @param sent       Number of files confirmed by PC so far.
     * @param total      Total files in the batch (0 = not yet known).
     */
    private void setTransferUiState(boolean inProgress, int sent, int total) {
        btnStart.setEnabled(false);
        btnStart.setAlpha(inProgress ? 0.7f : 0.4f);
        if (inProgress) {
            btnStart.setText(total > 0
                    ? getString(R.string.backup_backing_up_progress, sent, total)
                    : getString(R.string.backup_scanning));
        }
        // Lock mode cards and option controls to prevent mid-transfer reconfiguration.
        cardAllMedia.setClickable(!inProgress);
        cardFolder.setClickable(!inProgress);
        cbClassify.setEnabled(!inProgress);
        cbDeleteAfter.setEnabled(!inProgress);
        switchStorageSaver.setEnabled(!inProgress);
    }

    // ── Transfer result dialogs ───────────────────────────────────────────────

    /**
     * Shows the post-transfer summary dialog.
     *
     * <p>Reads {@link BackupViewModel#getTransferTotal()} and
     * {@link BackupViewModel#getFailedCount()} directly — these LiveData values are
     * still valid at dispatch time (see {@link #onTransferStatusChanged} Javadoc for
     * the LiveData ordering guarantee).
     *
     * <p>The dialog is not cancellable so the user must acknowledge it before the
     * fragment pops — this ensures they see the failure count rather than silently
     * returning to the dashboard.
     */
    private void showTransferSummaryDialog() {
        if (!isAdded()) {
            // Fragment was detached before we got here — pop defensively.
            requireActivity().getSupportFragmentManager().popBackStack();
            return;
        }
        Integer total  = backupViewModel.getTransferTotal().getValue();
        Integer failed = backupViewModel.getFailedCount().getValue();
        int t = (total  != null) ? total  : 0;
        int f = (failed != null) ? failed : 0;
        int succeeded = Math.max(0, t - f);

        String message = (f > 0)
                ? getString(R.string.backup_complete_dialog_msg_with_errors, succeeded, f)
                : getString(R.string.backup_complete_dialog_msg_all_ok, succeeded);

        new AlertDialog.Builder(requireContext())
                .setTitle(R.string.backup_complete_dialog_title)
                .setMessage(message)
                .setPositiveButton(android.R.string.ok,
                        (d, w) -> requireActivity().getSupportFragmentManager().popBackStack())
                .setCancelable(false)
                .show();
    }

    /**
     * Shows an error dialog for a catastrophic transport failure (the whole transfer
     * collapsed, not just one file).  Per-file failures are counted in the summary
     * dialog — this dialog is only shown for {@link BackupTransferStatus#FAILED}.
     */
    private void showTransferFailedDialog() {
        if (!isAdded()) {
            requireActivity().getSupportFragmentManager().popBackStack();
            return;
        }
        new AlertDialog.Builder(requireContext())
                .setTitle(R.string.backup_transfer_failed_title)
                .setMessage(R.string.backup_transfer_failed_msg)
                .setPositiveButton(android.R.string.ok,
                        (d, w) -> requireActivity().getSupportFragmentManager().popBackStack())
                .show();
    }

    // ── Parallel-slot auto-selection ──────────────────────────────────────────

    /**
     * Computes the optimal number of concurrent TauSync backup slots for this device.
     *
     * <p>Balancing factors:
     * <ul>
     *   <li><b>CPU cores</b> — {@link Runtime#availableProcessors()} gives the number
     *       of hardware threads available.  We use half the cores as a base so Android's
     *       background tasks and UI remain responsive during the backup.</li>
     *   <li><b>Battery level</b> — sending files concurrently puts extra load on the
     *       radio and CPU.  We throttle aggressively at low charge to prevent the phone
     *       dying mid-backup.  The live battery sticky broadcast is read once at scan
     *       time; no listener is registered.</li>
     *   <li><b>Practical ceiling of 4</b> — beyond 4 concurrent slots, WiFi bandwidth
     *       (typically the real bottleneck) is already saturated and adding threads only
     *       increases contention on the TauSync socket without improving throughput.</li>
     * </ul>
     *
     * <p>Thresholds:
     * <pre>
     *   battery &lt; 20 %  → 1 thread   (power-saver, strictly sequential)
     *   battery &lt; 40 %  → ≤ 2 threads (moderate throughput)
     *   battery ≥ 40 %  → min(cores/2, 4)  (full speed)
     * </pre>
     *
     * @return Number of parallel slots, always ≥ 1.
     */
    private int computeParallelSlots() {
        // ── CPU core count ────────────────────────────────────────────────────
        int cores = Runtime.getRuntime().availableProcessors();
        // Base: half the physical cores, min 1, max 4.
        // Rationale: storage I/O saturates before CPU; >4 threads adds contention.
        int base  = Math.max(1, Math.min(cores / 2, 4));

        // ── Battery level ─────────────────────────────────────────────────────
        int batteryPct = getCurrentBatteryPercent();
        Log.d(TAG, "computeParallelSlots: cores=" + cores
                + " base=" + base + " battery=" + batteryPct + "%");

        if (batteryPct < 20) return 1;               // power-saver
        if (batteryPct < 40) return Math.min(base, 2); // conservative
        return base;                                  // full speed
    }

    /**
     * Returns the current battery charge level as a percentage (0–100).
     *
     * <p>Reads the sticky {@link Intent#ACTION_BATTERY_CHANGED} broadcast synchronously —
     * no listener registration needed.  Returns 100 on any error so that a failure to
     * read battery state never causes us to throttle unnecessarily.
     *
     * @return Battery percentage 0–100, or 100 on error.
     */
    private int getCurrentBatteryPercent() {
        try {
            Intent batteryStatus = requireContext().registerReceiver(
                    null,
                    new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
            if (batteryStatus == null) return 100;
            int level = batteryStatus.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
            int scale = batteryStatus.getIntExtra(BatteryManager.EXTRA_SCALE, -1);
            if (level < 0 || scale <= 0) return 100;
            return (int) ((level / (float) scale) * 100);
        } catch (Exception e) {
            Log.w(TAG, "getCurrentBatteryPercent: could not read battery — defaulting to 100%");
            return 100;
        }
    }

}
