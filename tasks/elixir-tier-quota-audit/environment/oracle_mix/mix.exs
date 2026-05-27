defmodule Oracle.MixProject do
  use Mix.Project

  def project do
    [
      app: :oracle,
      version: "0.0.1",
      deps: deps()
    ]
  end

  defp deps do
    [{:jason, "~> 1.4"}]
  end
end
