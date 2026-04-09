package com.example.android.ui.adapters;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import com.example.android.R;
import com.example.android.ui.models.ToolItem;
import com.google.android.material.button.MaterialButton; // הוספנו את ה-Import הזה

import java.util.List;

public class ToolsAdapter extends RecyclerView.Adapter<ToolsAdapter.ToolViewHolder> {
    private List<ToolItem> tools;
    private OnToolClickListener listener;

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
        View view = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_tool, parent, false);
        return new ToolViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull ToolViewHolder holder, int position) {
        ToolItem tool = tools.get(position);

        // מעדכנים את הטקסט והאייקון של הכפתור
        holder.toolButton.setText(tool.getTitle());
        holder.toolButton.setIconResource(tool.getIconRes());

        // מאזין ללחיצה על הכפתור עצמו
        holder.toolButton.setOnClickListener(v -> listener.onToolClick(tool));
    }

    @Override
    public int getItemCount() { return tools.size(); }

    static class ToolViewHolder extends RecyclerView.ViewHolder {
        // הכפתור הוא עכשיו הרכיב המרכזי שלנו
        MaterialButton toolButton;

        ToolViewHolder(View itemView) {
            super(itemView);
            // אנחנו משתמשים ב-ID שנתנו ב-XML לכפתור (btnTool)
            toolButton = itemView.findViewById(R.id.btnTool);
        }
    }
}