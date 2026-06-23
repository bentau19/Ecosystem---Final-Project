package com.example.android.ui.fragments;

import android.Manifest;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.Matrix;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.annotation.NonNull;
import androidx.appcompat.widget.AppCompatButton;
import androidx.camera.core.CameraSelector;
import androidx.camera.core.ImageAnalysis;
import androidx.camera.core.ImageProxy;
import androidx.camera.core.Preview;
import androidx.camera.core.resolutionselector.ResolutionSelector;
import androidx.camera.core.resolutionselector.ResolutionStrategy;
import androidx.camera.lifecycle.ProcessCameraProvider;
import android.util.Size;
import androidx.camera.view.PreviewView;
import androidx.core.content.ContextCompat;
import androidx.fragment.app.Fragment;
import androidx.lifecycle.ViewModelProvider;

import com.example.android.R;
import com.example.android.domain.enums.WebcamStatus;
import com.example.android.repositories.WebcamRepository;
import com.example.android.viewmodel.WebcamViewModel;
import com.google.common.util.concurrent.ListenableFuture;

import java.io.ByteArrayOutputStream;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Full-screen viewfinder for the webcam streaming feature.
 *
 * Hosts two simultaneous CameraX use cases:
 *   - Preview  → feeds the on-screen PreviewView so the user can frame their shot.
 *   - ImageAnalysis → converts each frame to JPEG and pushes it into
 *     WebcamRepository.frameQueue for WebcamStreamUseCase to forward to the PC.
 *
 * The Start / Stop button drives WebcamViewModel — frame production is gated on
 * STREAMING status so no frames are sent before the user taps Start.
 */
public class WebcamFragment extends Fragment {

    private WebcamViewModel webcamViewModel;
    private PreviewView previewView;
    private AppCompatButton btnStream;
    private TextView tvStatus;

    private ExecutorService cameraExecutor;
    private ActivityResultLauncher<String> requestPermissionLauncher;
    private boolean useFrontCamera = false;

    // Throttle outbound frames to 15 fps so the Desktop pyvirtualcam (also 15 fps)
    // never accumulates a TCP backlog that would cause latency to grow over time.
    private static final long FRAME_INTERVAL_MS = 1000L / 15; // 66 ms
    private long lastQueuedFrameMs = 0;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        cameraExecutor = Executors.newSingleThreadExecutor();

        requestPermissionLauncher = registerForActivityResult(
            new ActivityResultContracts.RequestPermission(),
            granted -> {
                if (granted) {
                    startCamera();
                } else {
                    Toast.makeText(requireContext(),
                        "Camera permission is required for this feature.",
                        Toast.LENGTH_LONG).show();
                    requireActivity().onBackPressed();
                }
            }
        );
    }

    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, ViewGroup container,
                             Bundle savedInstanceState) {
        View view = inflater.inflate(R.layout.fragment_webcam, container, false);

        webcamViewModel = new ViewModelProvider(requireActivity()).get(WebcamViewModel.class);
        previewView   = view.findViewById(R.id.previewView);
        btnStream     = view.findViewById(R.id.btnStream);
        tvStatus      = view.findViewById(R.id.tvStatus);

        view.findViewById(R.id.btnBack).setOnClickListener(v ->
            requireActivity().onBackPressed());

        view.findViewById(R.id.btnFlipCamera).setOnClickListener(v -> {
            useFrontCamera = !useFrontCamera;
            startCamera();
        });

        btnStream.setOnClickListener(v -> {
            WebcamStatus status = webcamViewModel.getStatus().getValue();
            if (status == WebcamStatus.STREAMING) {
                webcamViewModel.stopStream();
            } else {
                webcamViewModel.startStream();
            }
        });

        webcamViewModel.getStatus().observe(getViewLifecycleOwner(), this::updateUi);

        if (ContextCompat.checkSelfPermission(requireContext(), Manifest.permission.CAMERA)
                == PackageManager.PERMISSION_GRANTED) {
            startCamera();
        } else {
            requestPermissionLauncher.launch(Manifest.permission.CAMERA);
        }

        return view;
    }

    // ── UI state ───────────────────────────────────────────────────────────────

    private void updateUi(WebcamStatus status) {
        if (status == WebcamStatus.STREAMING) {
            btnStream.setText("Stop Streaming");
            btnStream.setBackgroundTintList(
                ContextCompat.getColorStateList(requireContext(), R.color.accent_pink));
            tvStatus.setText("Streaming to PC...");
            tvStatus.setTextColor(
                ContextCompat.getColor(requireContext(), R.color.status_green));
        } else {
            btnStream.setText("Start Streaming");
            btnStream.setBackgroundTintList(
                ContextCompat.getColorStateList(requireContext(), R.color.accent_cyan));
            tvStatus.setText("Not streaming");
            tvStatus.setTextColor(
                ContextCompat.getColor(requireContext(), R.color.text_muted));
        }
    }

    // ── CameraX ────────────────────────────────────────────────────────────────

    private void startCamera() {
        ListenableFuture<ProcessCameraProvider> future =
            ProcessCameraProvider.getInstance(requireContext());

        future.addListener(() -> {
            if (getContext() == null || !isAdded()) return; // fragment already gone
            try {
                ProcessCameraProvider cameraProvider = future.get();

                // Use case 1: live preview on screen
                Preview preview = new Preview.Builder().build();
                preview.setSurfaceProvider(previewView.getSurfaceProvider());

                // Use case 2: frame analysis — RGBA_8888 avoids manual YUV conversion.
                // Cap at 640×480 to avoid OOM from 4K bitmaps (50 MB each).
                ResolutionStrategy resStrategy = new ResolutionStrategy(
                    new Size(640, 480),
                    ResolutionStrategy.FALLBACK_RULE_CLOSEST_LOWER_THEN_HIGHER
                );
                ImageAnalysis imageAnalysis = new ImageAnalysis.Builder()
                    .setResolutionSelector(new ResolutionSelector.Builder()
                        .setResolutionStrategy(resStrategy)
                        .build())
                    .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .build();
                imageAnalysis.setAnalyzer(cameraExecutor, this::processFrame);

                CameraSelector cameraSelector = useFrontCamera
                    ? CameraSelector.DEFAULT_FRONT_CAMERA
                    : CameraSelector.DEFAULT_BACK_CAMERA;

                cameraProvider.unbindAll();
                cameraProvider.bindToLifecycle(
                    getViewLifecycleOwner(),
                    cameraSelector,
                    preview,
                    imageAnalysis
                );

            } catch (Exception e) {
                Toast.makeText(requireContext(),
                    "Failed to start camera: " + e.getMessage(),
                    Toast.LENGTH_SHORT).show();
            }
        }, ContextCompat.getMainExecutor(requireContext()));
    }

    private void processFrame(ImageProxy imageProxy) {
        try {
            // Gate: only push frames when the user has tapped Start
            WebcamStatus status = webcamViewModel.getStatus().getValue();
            if (status != WebcamStatus.STREAMING) return;

            // Throttle to 15 fps — drops frames that arrive sooner than 66 ms after
            // the last queued frame, keeping TCP send rate equal to Desktop consume rate.
            long now = System.currentTimeMillis();
            if (now - lastQueuedFrameMs < FRAME_INTERVAL_MS) return;
            lastQueuedFrameMs = now;

            // RGBA_8888 → Bitmap directly (no YUV math required)
            Bitmap original = imageProxy.toBitmap();

            // Correct physical sensor orientation so the PC sees an upright image
            int rotation = imageProxy.getImageInfo().getRotationDegrees();
            Bitmap bitmap;
            if (rotation != 0) {
                Matrix matrix = new Matrix();
                matrix.postRotate(rotation);
                bitmap = Bitmap.createBitmap(
                    original, 0, 0, original.getWidth(), original.getHeight(), matrix, true);
                original.recycle(); // release the unrotated copy immediately
            } else {
                bitmap = original;
            }

            // Compress to JPEG, then immediately free the bitmap — 15 bitmaps/sec of
            // 1.2 MB each cause GC churn and micro-stutters if left to the collector.
            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            bitmap.compress(Bitmap.CompressFormat.JPEG, 70, baos);
            bitmap.recycle();
            byte[] jpegBytes = baos.toByteArray();

            // Drop-oldest if queue is full — always prefer fresh frames over buffering
            WebcamRepository repo = WebcamRepository.getInstance();
            if (!repo.frameQueue.offer(jpegBytes)) {
                repo.frameQueue.poll();
                repo.frameQueue.offer(jpegBytes);
            }
        } finally {
            imageProxy.close(); // must always be called or CameraX stalls
        }
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        cameraExecutor.shutdown();
    }
}
