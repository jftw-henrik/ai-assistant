import Foundation

enum CaptureAPI {
    static let endpoint = URL(string: "https://ai-assistant-production-45e5.up.railway.app/capture")!

    enum APIError: LocalizedError {
        case invalidResponse
        case serverError(String)

        var errorDescription: String? {
            switch self {
            case .invalidResponse:
                return "Invalid server response."
            case .serverError(let message):
                return message
            }
        }
    }

    static func capture(text: String) async throws -> String {
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(CaptureRequest(text: text))

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        let body = String(data: data, encoding: .utf8) ?? ""
        guard (200 ... 299).contains(http.statusCode) else {
            throw APIError.serverError(body.isEmpty ? "Request failed (\(http.statusCode))." : body)
        }
        return body.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

private struct CaptureRequest: Encodable {
    let text: String
}
