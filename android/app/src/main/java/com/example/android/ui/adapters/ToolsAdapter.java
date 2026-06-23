package com.example.android.ui.adapters;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import com.example.android.R;
import com.example.android.ui.models.ToolItem;
import com.google.android.material.button.MaterialButton;

import java.util.List;

/**
 * Adapter for managing and displaying the list of utility tools in the Actions screen.
 * Each tool is represented as a clickable MaterialButton within a RecyclerView.
 */
public class ToolsAdapter extends RecyclerView.Adapter<ToolsAdapter.ToolViewHolder> {
    private List<ToolItem> tools;
    private OnToolClickListener listener;

    /**
     * Interface to handle click events on specific tools.
     */
    public interface OnToolClickListener {
        void onToolClick(ToolItem tool);
    }

    public ToolsAdapter(List<ToolItem> tools, OnToolClickListener listener) {
        this.tools = tools;
        this.listener = listener;
    }

    @NonNull
    @Override
    public ToolViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        // Inflate the custom tool item layout
        View view = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_tool, parent, false);
        return new ToolViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull ToolViewHolder holder, int position) {
        ToolItem tool = tools.get(position);

        // Update button text and icon based on the tool data
        holder.toolButton.setText(tool.getTitle());
        holder.toolButton.setIconResource(tool.getIconRes());
        holder.toolButton.setEnabled(tool.isEnabled());
        holder.toolButton.setAlpha(tool.isEnabled() ? 1.0f : 0.5f);

        // Set click listener on the MaterialButton component
        holder.toolButton.setOnClickListener(v -> listener.onToolClick(tool));
    }

    @Override
    public int getItemCount() { return tools.size(); }

    /**
     * ViewHolder class that holds the reference to the MaterialButton in the layout.
     */
    static class ToolViewHolder extends RecyclerView.ViewHolder {
        // The MaterialButton is the primary interactive element in our item layout
        MaterialButton toolButton;

        ToolViewHolder(View itemView) {
            super(itemView);
            // Reference the specific ID (btnTool) defined in item_tool.xml
            toolButton = itemView.findViewById(R.id.btnTool);
        }
    }
}