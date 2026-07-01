import SwiftUI

struct CapturePanelView: View {
    var onClose: () -> Void
    @State private var input = ""
    @State private var status = "Capture tasks, ideas, or deadlines."
    @State private var statusIsError = false
    @State private var isLoading = false
    @State private var focusEditor = false
    @State private var contentOpacity = 0.0
    @State private var contentScale = 0.98

    var body: some View {
        ZStack {
            VisualEffectBackground(material: .hudWindow)
                .overlay {
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .strokeBorder(Color.white.opacity(0.12), lineWidth: 1)
                }

            VStack(alignment: .leading, spacing: 14) {
                HStack {
                    Image(systemName: "bolt.fill")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(.secondary)
                    Text("Quick Capture")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(.secondary)
                    Spacer()
                    Text("⌃⌥Space")
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(.tertiary)
                }

                CaptureTextView(
                    text: $input,
                    onSubmit: submit,
                    onEscape: close,
                    requestFocus: focusEditor
                )
                .frame(minHeight: 88, maxHeight: 160)
                .disabled(isLoading)

                HStack(alignment: .firstTextBaseline) {
                    Text(status)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(statusIsError ? Color.red.opacity(0.9) : Color.secondary)
                        .lineLimit(4)
                        .frame(maxWidth: .infinity, alignment: .leading)

                    if isLoading {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Text("↩ capture")
                            .font(.system(size: 11, weight: .medium, design: .rounded))
                            .foregroundStyle(.tertiary)
                    }
                }
            }
            .padding(18)
            .opacity(contentOpacity)
            .scaleEffect(contentScale)
        }
        .frame(width: 560, height: 220)
        .preferredColorScheme(.dark)
        .onAppear {
            focusEditor = true
            withAnimation(.spring(response: 0.28, dampingFraction: 0.86)) {
                contentOpacity = 1
                contentScale = 1
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .quickCaptureFocus)) { _ in
            focusEditor = false
            DispatchQueue.main.async {
                focusEditor = true
            }
        }
        .onDisappear {
            contentOpacity = 0
            contentScale = 0.98
        }
    }

    private func submit() {
        let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !isLoading else { return }

        isLoading = true
        statusIsError = false
        status = "Sending…"

        Task {
            do {
                let response = try await CaptureAPI.capture(text: trimmed)
                await MainActor.run {
                    isLoading = false
                    status = response
                    statusIsError = response.hasPrefix("❌")
                    if !statusIsError {
                        input = ""
                    }
                    focusEditor = true
                }
            } catch {
                await MainActor.run {
                    isLoading = false
                    statusIsError = true
                    status = "❌ Error: \(error.localizedDescription)"
                    focusEditor = true
                }
            }
        }
    }

    private func close() {
        withAnimation(.easeOut(duration: 0.16)) {
            contentOpacity = 0
            contentScale = 0.98
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.12) {
            onClose()
        }
    }
}
