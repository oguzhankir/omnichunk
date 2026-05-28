defmodule Inventory do
  @moduledoc """
  In-memory inventory store with simple counters.
  """

  use GenServer
  import Logger
  alias Inventory.Item
  require IEx

  defmacro debug_count(name) do
    quote do
      IO.puts("count=#{count(unquote(name))}")
    end
  end

  def start_link(opts) do
    GenServer.start_link(__MODULE__, %{}, opts)
  end

  def add(name, qty \\ 1) when is_binary(name) and is_integer(qty) and qty > 0 do
    GenServer.cast(__MODULE__, {:add, name, qty})
  end

  def count(name) do
    GenServer.call(__MODULE__, {:count, name})
  end

  defp normalize(name) do
    String.downcase(name)
  end
end

defmodule Inventory.Item do
  defstruct [:name, :qty]

  def new(name, qty), do: %__MODULE__{name: name, qty: qty}
end
